from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FixtureProject:
    project_root: Path
    project_file: Path
    village_square: Path
    village_house: Path
    title_screen: Path
    showcase_tiles: Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
    )


def _write_solid_png(path: Path, width: int, height: int, rgba: tuple[int, int, int, int]) -> None:
    r, g, b, a = rgba
    row = b"\x00" + bytes([r, g, b, a]) * width
    raw = row * height
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw))
        + _png_chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def create_editor_fixture_project(root: Path) -> FixtureProject:
    project_root = root / "fixture_project"
    project_file = project_root / "project.json"
    village_square = project_root / "areas" / "village_square.json"
    village_house = project_root / "areas" / "village_house.json"
    title_screen = project_root / "areas" / "title_screen.json"
    showcase_tiles = project_root / "assets" / "project" / "tiles" / "showcase_tiles.png"

    _write_solid_png(showcase_tiles, 96, 16, (80, 180, 100, 255))
    _write_solid_png(
        project_root / "assets" / "project" / "ui" / "dialogue_panel.png",
        64,
        32,
        (40, 60, 90, 255),
    )

    _write_json(
        project_file,
        {
            "startup_area": "areas/title_screen",
            "area_paths": ["areas/"],
            "entity_template_paths": ["entity_templates/"],
            "asset_paths": ["assets/"],
            "command_paths": ["commands/"],
            "dialogue_paths": ["dialogues/"],
            "item_paths": ["items/"],
            "shared_variables_path": "shared_variables.json",
            "global_entities": [
                {"id": "dialogue_controller"},
                {"id": "pause_controller", "template": "entity_templates/pause_controller"},
                {"id": "debug_controller"},
            ],
        },
    )

    _write_json(
        project_root / "shared_variables.json",
        {
            "display": {
                "internal_width": 256,
                "internal_height": 192,
            }
        },
    )

    _write_json(
        project_root / "entity_templates" / "area_door.json",
        {
            "kind": "door",
            "visuals": [],
        },
    )
    _write_json(
        project_root / "entity_templates" / "pause_controller.json",
        {
            "kind": "system",
            "space": "screen",
            "visuals": [],
        },
    )

    _write_json(
        project_root / "items" / "apple.json",
        {
            "name": "Apple",
            "max_stack": 9,
        },
    )
    _write_json(
        project_root / "items" / "copper_key.json",
        {
            "name": "Copper Key",
            "max_stack": 1,
        },
    )
    _write_json(
        project_root / "commands" / "system" / "do_thing.json",
        {
            "commands": [],
        },
    )

    base_tileset = {
        "firstgid": 1,
        "path": "assets/project/tiles/showcase_tiles.png",
        "tile_width": 16,
        "tile_height": 16,
    }

    _write_json(
        village_square,
        {
            "tile_size": 16,
            "tilesets": [base_tileset],
            "tile_layers": [
                {
                    "name": "ground",
                    "render_order": 0,
                    "y_sort": False,
                    "stack_order": 0,
                    "grid": [[1, 2, 3], [4, 5, 6]],
                },
                {
                    "name": "structure",
                    "render_order": 10,
                    "y_sort": False,
                    "stack_order": 0,
                    "grid": [[0, 6, 0], [0, 0, 0]],
                },
                {
                    "name": "overlay",
                    "render_order": 20,
                    "y_sort": False,
                    "stack_order": 0,
                    "grid": [[0, 0, 0], [0, 3, 0]],
                },
            ],
            "entities": [
                {
                    "id": "player",
                    "grid_x": 1,
                    "grid_y": 1,
                    "template": "entity_templates/area_door",
                }
            ],
            "variables": {},
        },
    )

    _write_json(
        village_house,
        {
            "tile_size": 16,
            "tilesets": [base_tileset],
            "tile_layers": [
                {
                    "name": "ground",
                    "render_order": 0,
                    "y_sort": False,
                    "stack_order": 0,
                    "grid": [[1, 2], [3, 4]],
                },
                {
                    "name": "structure",
                    "render_order": 10,
                    "y_sort": False,
                    "stack_order": 0,
                    "grid": [[0, 5], [0, 6]],
                },
                {
                    "name": "overlay",
                    "render_order": 20,
                    "y_sort": False,
                    "stack_order": 0,
                    "grid": [[3, 0], [0, 0]],
                },
            ],
            "entities": [
                {
                    "id": "house_lever",
                    "grid_x": 0,
                    "grid_y": 1,
                }
            ],
            "variables": {},
        },
    )

    _write_json(
        title_screen,
        {
            "tile_size": 16,
            "tilesets": [],
            "tile_layers": [],
            "entities": [
                {
                    "id": "title_logo",
                    "space": "screen",
                    "pixel_x": 48,
                    "pixel_y": 24,
                },
                {
                    "id": "start_prompt",
                    "space": "screen",
                    "pixel_x": 80,
                    "pixel_y": 96,
                },
            ],
            "variables": {},
        },
    )

    return FixtureProject(
        project_root=project_root,
        project_file=project_file,
        village_square=village_square,
        village_house=village_house,
        title_screen=title_screen,
        showcase_tiles=showcase_tiles,
    )
