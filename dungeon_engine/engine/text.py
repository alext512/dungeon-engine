"""Bitmap-font loading and rendering for pixel-art friendly UI text."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pygame

from dungeon_engine import config
from dungeon_engine.engine.asset_manager import AssetManager


@dataclass(slots=True)
class BitmapGlyph:
    """A single trimmed glyph plus its draw offsets and advance width."""

    surface: pygame.Surface
    offset_x: int
    offset_y: int
    advance: int


@dataclass(slots=True)
class BitmapFont:
    """A variable-width bitmap font loaded from a sheet plus JSON metadata."""

    font_id: str
    line_height: int
    letter_spacing: int
    space_width: int
    fallback_character: str
    glyphs: dict[str, BitmapGlyph]
    _tinted_cache: dict[tuple[str, tuple[int, int, int]], pygame.Surface] = field(
        default_factory=dict
    )

    def measure_text(self, text: str) -> tuple[int, int]:
        """Return the pixel width and height for the provided text block."""
        if not text:
            return (0, self.line_height)

        max_width = 0
        line_width = 0
        line_count = 1
        previous_drawn = False
        for character in text:
            if character == "\n":
                max_width = max(max_width, line_width)
                line_width = 0
                line_count += 1
                previous_drawn = False
                continue

            if character == " ":
                line_width += self.space_width
                previous_drawn = True
                continue

            glyph = self._lookup_glyph(character)
            if glyph is None:
                continue

            if previous_drawn:
                line_width += self.letter_spacing
            line_width += glyph.advance
            previous_drawn = True

        max_width = max(max_width, line_width)
        return (max_width, line_count * self.line_height)

    def render_text(
        self,
        target_surface: pygame.Surface,
        text: str,
        position: tuple[int, int],
        color: tuple[int, int, int],
    ) -> None:
        """Draw the provided text block using the configured bitmap font."""
        start_x, start_y = position
        draw_x = start_x
        draw_y = start_y
        previous_drawn = False

        for character in text:
            if character == "\n":
                draw_x = start_x
                draw_y += self.line_height
                previous_drawn = False
                continue

            if character == " ":
                draw_x += self.space_width
                previous_drawn = True
                continue

            glyph = self._lookup_glyph(character)
            if glyph is None:
                continue

            if previous_drawn:
                draw_x += self.letter_spacing

            target_surface.blit(
                self._get_tinted_glyph(character, color),
                (draw_x + glyph.offset_x, draw_y + glyph.offset_y),
            )
            draw_x += glyph.advance
            previous_drawn = True

    def _lookup_glyph(self, character: str) -> BitmapGlyph | None:
        """Return a glyph or fall back to the configured replacement character."""
        glyph = self.glyphs.get(character)
        if glyph is not None:
            return glyph
        return self.glyphs.get(self.fallback_character)

    def _get_tinted_glyph(
        self,
        character: str,
        color: tuple[int, int, int],
    ) -> pygame.Surface:
        """Return a cached colorized glyph surface."""
        glyph = self._lookup_glyph(character)
        if glyph is None:
            raise KeyError(f"Font '{self.font_id}' has no glyph for '{character}'.")

        cache_key = (character if character in self.glyphs else self.fallback_character, color)
        cached = self._tinted_cache.get(cache_key)
        if cached is not None:
            return cached

        tinted = glyph.surface.copy()
        tinted.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MULT)
        self._tinted_cache[cache_key] = tinted
        return tinted


class TextRenderer:
    """Load configurable fonts by id and render text blocks with them."""

    def __init__(self, asset_manager: AssetManager) -> None:
        self.asset_manager = asset_manager
        self._font_cache: dict[str, BitmapFont] = {}

    def measure_text(self, text: str, *, font_id: str = config.DEFAULT_UI_FONT_ID) -> tuple[int, int]:
        """Return width and height for text rendered with the requested font."""
        return self.get_font(font_id).measure_text(text)

    def line_height(self, *, font_id: str = config.DEFAULT_UI_FONT_ID) -> int:
        """Return the configured line height for the requested font."""
        return self.get_font(font_id).line_height

    def render_text(
        self,
        target_surface: pygame.Surface,
        text: str,
        position: tuple[int, int],
        color: tuple[int, int, int],
        *,
        font_id: str = config.DEFAULT_UI_FONT_ID,
    ) -> None:
        """Draw text with the named font onto the provided surface."""
        self.get_font(font_id).render_text(target_surface, text, position, color)

    def wrap_text(
        self,
        text: str,
        max_width: int,
        *,
        font_id: str = config.DEFAULT_UI_FONT_ID,
    ) -> str:
        """Wrap text to fit within a maximum pixel width."""
        if max_width <= 0 or not text:
            return text

        wrapped_lines: list[str] = []
        for source_line in text.split("\n"):
            if source_line == "":
                wrapped_lines.append("")
                continue

            current_line = ""
            for word in source_line.split(" "):
                candidate = word if current_line == "" else f"{current_line} {word}"
                if current_line and self.measure_text(candidate, font_id=font_id)[0] > max_width:
                    wrapped_lines.append(current_line)
                    current_line = self._wrap_long_word(
                        word,
                        max_width,
                        font_id=font_id,
                        output=wrapped_lines,
                    )
                    continue

                if self.measure_text(candidate, font_id=font_id)[0] > max_width:
                    current_line = self._wrap_long_word(
                        word,
                        max_width,
                        font_id=font_id,
                        output=wrapped_lines,
                    )
                    continue

                current_line = candidate

            wrapped_lines.append(current_line)

        return "\n".join(wrapped_lines)

    def get_font(self, font_id: str) -> BitmapFont:
        """Load a named font once and return it from cache afterwards."""
        cached = self._font_cache.get(font_id)
        if cached is not None:
            return cached

        font = self._load_font(font_id)
        self._font_cache[font_id] = font
        return font

    def _load_font(self, font_id: str) -> BitmapFont:
        """Load a font definition from JSON and build runtime glyph objects."""
        definition_path = self._resolve_font_definition_path(font_id)
        if not definition_path.exists():
            raise FileNotFoundError(f"Missing font definition '{definition_path}'.")

        definition = json.loads(definition_path.read_text(encoding="utf-8"))
        kind = definition.get("kind", "bitmap")
        if kind != "bitmap":
            raise ValueError(f"Unsupported font kind '{kind}' in '{definition_path}'.")

        glyph_order = str(definition["glyph_order"])
        cell_width = int(definition["cell_width"])
        cell_height = int(definition["cell_height"])
        columns = int(definition.get("columns", len(glyph_order)))
        line_height = int(definition.get("line_height", cell_height))
        letter_spacing = int(definition.get("letter_spacing", 1))
        space_width = int(definition.get("space_width", cell_width // 2))
        fallback_character = str(definition.get("fallback_character", "?"))
        minimum_advance = int(definition.get("minimum_advance", 1))
        advance_overrides = {
            str(character): int(width)
            for character, width in dict(definition.get("advance_overrides", {})).items()
        }

        atlas = self.asset_manager.get_image(str(definition["atlas"]))
        glyphs: dict[str, BitmapGlyph] = {}
        for index, character in enumerate(glyph_order):
            column = index % columns
            row = index // columns
            source_rect = pygame.Rect(
                column * cell_width,
                row * cell_height,
                cell_width,
                cell_height,
            )
            cell_surface = pygame.Surface((cell_width, cell_height), pygame.SRCALPHA)
            cell_surface.blit(atlas, (0, 0), source_rect)
            bounds = cell_surface.get_bounding_rect(min_alpha=1)
            if bounds.width == 0 or bounds.height == 0:
                glyph_surface = pygame.Surface((1, 1), pygame.SRCALPHA)
                offset_x = 0
                offset_y = 0
                advance = advance_overrides.get(character, minimum_advance)
            else:
                white_cell = self._to_white_mask(cell_surface)
                glyph_surface = white_cell.subsurface(bounds).copy()
                offset_x = bounds.x
                offset_y = bounds.y
                advance = advance_overrides.get(
                    character,
                    max(minimum_advance, bounds.width),
                )
            glyphs[character] = BitmapGlyph(
                surface=glyph_surface,
                offset_x=offset_x,
                offset_y=offset_y,
                advance=advance,
            )

        return BitmapFont(
            font_id=font_id,
            line_height=line_height,
            letter_spacing=letter_spacing,
            space_width=space_width,
            fallback_character=fallback_character,
            glyphs=glyphs,
        )

    def _resolve_font_definition_path(self, font_id: str) -> Path:
        """Resolve a font definition from the active project first, then legacy fallback."""
        project = getattr(self.asset_manager, "_project", None)
        if project is not None:
            for asset_dir in project.asset_paths:
                candidate = asset_dir / "fonts" / f"{font_id}.json"
                if candidate.exists():
                    return candidate
                for recursive_candidate in sorted(asset_dir.rglob(f"{font_id}.json")):
                    if recursive_candidate.is_file():
                        return recursive_candidate
        return config.FONTS_DIR / f"{font_id}.json"

    def _to_white_mask(self, source_surface: pygame.Surface) -> pygame.Surface:
        """Convert a glyph cell to a white alpha mask so it can be tinted later."""
        mask = pygame.mask.from_surface(source_surface)
        return mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))

    def _wrap_long_word(
        self,
        word: str,
        max_width: int,
        *,
        font_id: str,
        output: list[str],
    ) -> str:
        """Split a long word across multiple lines when needed."""
        current = ""
        for character in word:
            candidate = f"{current}{character}"
            if current and self.measure_text(candidate, font_id=font_id)[0] > max_width:
                output.append(current)
                current = character
            else:
                current = candidate
        return current

