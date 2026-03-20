"""Shared configuration values for the runtime and starter content."""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DATA_DIR = PACKAGE_ROOT / "data"
AREAS_DIR = DATA_DIR / "areas"
ENTITIES_DIR = DATA_DIR / "entities"
ASSETS_DIR = DATA_DIR / "assets"
TILES_DIR = ASSETS_DIR / "tiles"
FONTS_DIR = DATA_DIR / "fonts"
LOGS_DIR = PROJECT_ROOT / "logs"
ERROR_LOG_PATH = LOGS_DIR / "error.log"
SAVES_DIR = PROJECT_ROOT / "saves"
DEFAULT_SAVE_SLOT_PATH = SAVES_DIR / "slot_1.json"

WINDOW_TITLE = "Python Puzzle Engine"
INTERNAL_WIDTH = 320
INTERNAL_HEIGHT = 240
SCALE = 3
FPS = 60
DEFAULT_TILE_SIZE = 16
MOVE_DURATION_SECONDS = 0.14
PIXEL_ART_MODE = True
EDITOR_CAMERA_PAN_SPEED = 180.0
DEFAULT_UI_FONT_ID = "pixelbet"
DEFAULT_DIALOGUE_FONT_ID = "pixelbet"

COLOR_BACKGROUND = (18, 20, 26)
COLOR_FLOOR = (74, 85, 104)
COLOR_WALL = (41, 48, 62)
COLOR_GRID_ACCENT = (108, 122, 143)
COLOR_TEXT = (238, 242, 248)
