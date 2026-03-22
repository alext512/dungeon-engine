"""Screen-space elements rendered above the world."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from dungeon_engine import config


ScreenElementKind = Literal["image", "text"]
ScreenAnchor = Literal[
    "topleft",
    "top",
    "topright",
    "left",
    "center",
    "right",
    "bottomleft",
    "bottom",
    "bottomright",
]


@dataclass(slots=True)
class ScreenAnimationPlayback:
    """Runtime playback state for a screen-space image animation."""

    active: bool = False
    frame_sequence: list[int] = field(default_factory=list)
    ticks_per_frame: int = 1
    current_sequence_index: int = 0
    ticks_on_current_frame: int = 0
    hold_last_frame: bool = True


@dataclass(slots=True)
class ScreenElement:
    """A single screen-space image or text element."""

    element_id: str
    kind: ScreenElementKind
    layer: int = 0
    order: int = 0
    x: float = 0.0
    y: float = 0.0
    anchor: ScreenAnchor = "topleft"
    visible: bool = True
    asset_path: str | None = None
    frame_width: int | None = None
    frame_height: int | None = None
    frame_index: int = 0
    flip_x: bool = False
    tint: tuple[int, int, int] = (255, 255, 255)
    text: str = ""
    font_id: str = config.DEFAULT_UI_FONT_ID
    color: tuple[int, int, int] = config.COLOR_TEXT
    max_width: int | None = None
    animation: ScreenAnimationPlayback = field(default_factory=ScreenAnimationPlayback)


class ScreenElementManager:
    """Own a small collection of screen-space elements and their animations."""

    def __init__(self) -> None:
        self._elements: dict[str, ScreenElement] = {}
        self._next_order = 0

    def show_image(
        self,
        *,
        element_id: str,
        asset_path: str,
        x: float,
        y: float,
        frame_width: int | None = None,
        frame_height: int | None = None,
        frame: int = 0,
        layer: int = 0,
        anchor: ScreenAnchor = "topleft",
        flip_x: bool = False,
        tint: tuple[int, int, int] = (255, 255, 255),
        visible: bool = True,
    ) -> ScreenElement:
        """Create or replace an image element."""
        element = self._elements.get(element_id)
        order = element.order if element is not None else self._claim_order()
        self._elements[element_id] = ScreenElement(
            element_id=element_id,
            kind="image",
            layer=int(layer),
            order=order,
            x=float(x),
            y=float(y),
            anchor=anchor,
            visible=bool(visible),
            asset_path=str(asset_path),
            frame_width=int(frame_width) if frame_width is not None else None,
            frame_height=int(frame_height) if frame_height is not None else None,
            frame_index=int(frame),
            flip_x=bool(flip_x),
            tint=tuple(int(channel) for channel in tint),
        )
        return self._elements[element_id]

    def show_text(
        self,
        *,
        element_id: str,
        text: str,
        x: float,
        y: float,
        layer: int = 0,
        anchor: ScreenAnchor = "topleft",
        color: tuple[int, int, int] = config.COLOR_TEXT,
        font_id: str = config.DEFAULT_UI_FONT_ID,
        max_width: int | None = None,
        visible: bool = True,
    ) -> ScreenElement:
        """Create or replace a text element."""
        element = self._elements.get(element_id)
        order = element.order if element is not None else self._claim_order()
        self._elements[element_id] = ScreenElement(
            element_id=element_id,
            kind="text",
            layer=int(layer),
            order=order,
            x=float(x),
            y=float(y),
            anchor=anchor,
            visible=bool(visible),
            text=str(text),
            font_id=str(font_id),
            color=tuple(int(channel) for channel in color),
            max_width=int(max_width) if max_width is not None else None,
        )
        return self._elements[element_id]

    def set_text(self, element_id: str, text: str) -> None:
        """Replace the text content of an existing text element."""
        element = self.get_element(element_id)
        if element is None:
            raise KeyError(f"Screen element '{element_id}' not found.")
        if element.kind != "text":
            raise ValueError(f"Screen element '{element_id}' is not text.")
        element.text = str(text)

    def remove(self, element_id: str) -> None:
        """Remove one screen element if it exists."""
        self._elements.pop(element_id, None)

    def clear(self, *, layer: int | None = None) -> None:
        """Remove all screen elements, optionally only from one layer."""
        if layer is None:
            self._elements.clear()
            return
        self._elements = {
            element_id: element
            for element_id, element in self._elements.items()
            if element.layer != int(layer)
        }

    def get_element(self, element_id: str) -> ScreenElement | None:
        """Return one screen element by id."""
        return self._elements.get(element_id)

    def iter_elements(self) -> list[ScreenElement]:
        """Return all elements in render order."""
        return sorted(self._elements.values(), key=lambda item: (item.layer, item.order, item.element_id))

    def start_animation(
        self,
        *,
        element_id: str,
        frame_sequence: list[int],
        ticks_per_frame: int = 1,
        hold_last_frame: bool = True,
    ) -> None:
        """Start a one-shot frame animation on an existing image element."""
        element = self.get_element(element_id)
        if element is None:
            raise KeyError(f"Screen element '{element_id}' not found.")
        if element.kind != "image":
            raise ValueError(f"Screen element '{element_id}' is not an image.")
        if not frame_sequence:
            raise ValueError("Screen animation frame sequence cannot be empty.")
        if ticks_per_frame <= 0:
            raise ValueError("ticks_per_frame must be positive.")

        element.frame_index = int(frame_sequence[0])
        element.animation = ScreenAnimationPlayback(
            active=True,
            frame_sequence=[int(frame) for frame in frame_sequence],
            ticks_per_frame=int(ticks_per_frame),
            current_sequence_index=0,
            ticks_on_current_frame=0,
            hold_last_frame=bool(hold_last_frame),
        )

    def is_animating(self, element_id: str) -> bool:
        """Return True while an element's screen animation is active."""
        element = self.get_element(element_id)
        return bool(element is not None and element.animation.active)

    def update_tick(self) -> None:
        """Advance all active screen-space animations by one simulation tick."""
        for element in self._elements.values():
            if not element.visible or element.kind != "image":
                continue
            playback = element.animation
            if not playback.active or not playback.frame_sequence:
                continue

            playback.ticks_on_current_frame += 1
            if playback.ticks_on_current_frame < playback.ticks_per_frame:
                continue

            playback.ticks_on_current_frame = 0
            playback.current_sequence_index += 1
            if playback.current_sequence_index >= len(playback.frame_sequence):
                playback.active = False
                playback.current_sequence_index = len(playback.frame_sequence) - 1
                if playback.hold_last_frame:
                    element.frame_index = playback.frame_sequence[-1]
                continue

            element.frame_index = playback.frame_sequence[playback.current_sequence_index]

    def _claim_order(self) -> int:
        """Return a stable insertion-order slot for a new element."""
        order = self._next_order
        self._next_order += 1
        return order
