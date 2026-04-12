"""Engine-owned inventory session runtime for the first canonical inventory UI path."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from dungeon_engine.commands.context_types import InventoryRuntimeLike
from dungeon_engine.commands.runner import CommandContext, CommandHandle
from dungeon_engine.items import load_item_definition


def _deep_merge_dict(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Return one recursively merged dictionary without mutating either input."""
    merged = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(dict(merged[key]), value)
            continue
        merged[key] = copy.deepcopy(value)
    return merged


@dataclass(slots=True)
class InventorySession:
    """One active engine-owned inventory session."""

    entity_id: str
    ui_preset_name: str
    ui_preset: dict[str, Any]
    selected_index: int = 0
    scroll_offset: int = 0
    action_popup_open: bool = False
    action_index: int = 0


class InventorySessionWaitHandle(CommandHandle):
    """Wait until one specific inventory session closes."""

    def __init__(self, runtime: InventoryRuntimeLike, session: InventorySession) -> None:
        super().__init__()
        self.runtime = runtime
        self.session = session
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Complete once the tracked session is no longer the active inventory session."""
        _ = dt
        self.complete = not self.runtime.is_session_live(self.session)


class InventoryRuntime:
    """Own the active inventory session, UI rendering, and modal input behavior."""

    LIST_PANEL_ELEMENT_ID = "engine_inventory_list_panel"
    DETAIL_PANEL_ELEMENT_ID = "engine_inventory_detail_panel"
    DETAIL_PORTRAIT_ELEMENT_ID = "engine_inventory_detail_portrait"
    DETAIL_TEXT_ELEMENT_ID = "engine_inventory_detail_text"
    ACTION_PANEL_ELEMENT_ID = "engine_inventory_action_panel"
    MAX_VISIBLE_ROWS = 24

    def __init__(
        self,
        *,
        project: Any,
        screen_manager: Any,
        text_renderer: Any,
        command_context: CommandContext,
    ) -> None:
        self.project = project
        self.screen_manager = screen_manager
        self.text_renderer = text_renderer
        self.command_context = command_context
        self.current_session: InventorySession | None = None
        self.row_icon_element_ids = [
            f"engine_inventory_row_icon_{index}" for index in range(self.MAX_VISIBLE_ROWS)
        ]
        self.row_text_element_ids = [
            f"engine_inventory_row_text_{index}" for index in range(self.MAX_VISIBLE_ROWS)
        ]
        self.row_quantity_element_ids = [
            f"engine_inventory_row_quantity_{index}" for index in range(self.MAX_VISIBLE_ROWS)
        ]
        self.popup_option_element_ids = [
            "engine_inventory_action_option_0",
            "engine_inventory_action_option_1",
        ]

    def is_active(self) -> bool:
        """Return whether any inventory session is currently open."""
        return self.current_session is not None

    def has_pending_work(self) -> bool:
        """Return whether the inventory UI is currently modal."""
        return self.current_session is not None

    def is_session_live(self, session: InventorySession) -> bool:
        """Return whether the provided session is the active inventory session."""
        return self.current_session is session

    def update(self, dt: float) -> None:
        """Advance one inventory session tick.

        Inventory UI V1 does not currently animate or time any behavior.
        """
        _ = dt
        return

    def open_session(
        self,
        *,
        entity_id: str,
        ui_preset_name: str | None = None,
    ) -> InventorySession:
        """Open one inventory session for an entity-owned inventory."""
        resolved_entity_id = str(entity_id).strip()
        if not resolved_entity_id:
            raise ValueError("open_inventory_session requires a non-empty entity_id.")
        if self.command_context.world.get_entity(resolved_entity_id) is None:
            raise KeyError(f"Cannot open inventory for missing entity '{resolved_entity_id}'.")

        preset_name, preset = self._resolve_ui_preset(
            explicit_preset_name=ui_preset_name,
        )
        session = InventorySession(
            entity_id=resolved_entity_id,
            ui_preset_name=preset_name,
            ui_preset=copy.deepcopy(preset),
        )
        if self.current_session is not None:
            self._clear_ui()
        self.current_session = session
        self._sync_selection_and_scroll(session)
        self._render_session(session)
        return session

    def close_current_session(self) -> None:
        """Close the active inventory session when one exists."""
        if self.current_session is None:
            return
        self._clear_ui()
        self.current_session = None

    def handle_action(self, action_name: str) -> bool:
        """Consume one logical input action when an inventory session is active."""
        session = self.current_session
        if session is None:
            return False

        action = str(action_name).strip()
        if not action:
            return False

        if action == "inventory":
            self.close_current_session()
            return True

        if session.action_popup_open:
            if action == "menu":
                session.action_popup_open = False
                session.action_index = 0
                self._render_session(session)
                return True
            if action == "interact":
                self._confirm_action_popup(session)
                return True
            if action == "move_up":
                self._move_action_selection(session, delta=-1)
                return True
            if action == "move_down":
                self._move_action_selection(session, delta=1)
                return True
            if action in {"move_left", "move_right"}:
                return True
            return False

        if action == "menu":
            self.close_current_session()
            return True

        if action == "move_up":
            self._move_selection(session, delta=-1)
            return True
        if action == "move_down":
            self._move_selection(session, delta=1)
            return True
        if action in {"move_left", "move_right"}:
            return True
        if action == "interact":
            self._open_action_popup_or_deny(session)
            return True
        return False

    def _resolve_ui_preset(
        self,
        *,
        explicit_preset_name: str | None,
    ) -> tuple[str, dict[str, Any]]:
        """Resolve one inventory UI preset, allowing sparse project overrides."""
        inventory_ui = self.project.shared_variables.get("inventory_ui", {})
        default_preset = self._default_ui_preset()
        if not isinstance(inventory_ui, dict):
            return "engine_default", default_preset

        presets = inventory_ui.get("presets", {})
        if not isinstance(presets, dict) or not presets:
            return "engine_default", default_preset

        preset_name = str(explicit_preset_name).strip() if explicit_preset_name not in (None, "") else ""
        if not preset_name:
            preset_name = str(inventory_ui.get("default_preset", "standard")).strip() or "standard"
        raw_preset = presets.get(preset_name)
        if not isinstance(raw_preset, dict):
            raise KeyError(f"Unknown inventory UI preset '{preset_name}'.")
        return preset_name, _deep_merge_dict(default_preset, raw_preset)

    def _default_ui_preset(self) -> dict[str, Any]:
        """Return the built-in fallback inventory UI preset."""
        return {
            "list_panel": {
                "path": "assets/project/ui/dialogue_panel.png",
                "x": 0,
                "y": 96,
            },
            "list": {
                "x": 8,
                "y": 102,
                "width": 140,
                "visible_rows": 4,
                "row_height": 10,
                "icon_size": 16,
                "icon_gap": 4,
                "quantity_gap": 6,
            },
            "detail_panel": {
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
                "plain": {"x": 8, "y": 154, "width": 240, "max_lines": 3},
                "with_portrait": {"x": 56, "y": 154, "width": 192, "max_lines": 3},
            },
            "action_popup": {
                "panel": {
                    "path": "assets/project/ui/dialogue_panel.png",
                    "x": 152,
                    "y": 96,
                },
                "x": 160,
                "y": 102,
                "width": 72,
                "row_height": 10,
            },
            "font_id": "pixelbet",
            "text_color": [245, 232, 190],
            "choice_text_color": [238, 242, 248],
            "ui_layer": 100,
            "text_layer": 101,
            "deny_sfx_path": None,
        }

    def _render_session(self, session: InventorySession) -> None:
        """Render the active inventory list, detail panel, and optional popup."""
        if self.current_session is not session:
            return

        self._clear_ui()
        ui_layer = int(session.ui_preset.get("ui_layer", 100))
        text_layer = int(session.ui_preset.get("text_layer", 101))

        list_panel = dict(session.ui_preset.get("list_panel", {}))
        self.screen_manager.show_image(
            element_id=self.LIST_PANEL_ELEMENT_ID,
            asset_path=str(list_panel.get("path", "assets/project/ui/dialogue_panel.png")),
            x=float(list_panel.get("x", 0)),
            y=float(list_panel.get("y", 96)),
            layer=ui_layer,
        )

        detail_panel = dict(session.ui_preset.get("detail_panel", {}))
        self.screen_manager.show_image(
            element_id=self.DETAIL_PANEL_ELEMENT_ID,
            asset_path=str(detail_panel.get("path", "assets/project/ui/dialogue_panel.png")),
            x=float(detail_panel.get("x", 0)),
            y=float(detail_panel.get("y", 148)),
            layer=ui_layer,
        )

        self._render_item_rows(session, layer=text_layer)
        self._render_detail_panel(session, layer=text_layer)
        if session.action_popup_open:
            self._render_action_popup(session, ui_layer=ui_layer, text_layer=text_layer)

    def _render_item_rows(self, session: InventorySession, *, layer: int) -> None:
        """Render the visible item-row window."""
        list_layout = dict(session.ui_preset.get("list", {}))
        list_x = float(list_layout.get("x", 8))
        list_y = float(list_layout.get("y", 102))
        list_width = max(1, int(list_layout.get("width", 140)))
        row_height = max(1.0, float(list_layout.get("row_height", 10)))
        visible_rows = max(1, min(self.MAX_VISIBLE_ROWS, int(list_layout.get("visible_rows", 4))))
        icon_size = max(0, int(list_layout.get("icon_size", 16)))
        icon_gap = max(0, int(list_layout.get("icon_gap", 4)))
        quantity_gap = max(0, int(list_layout.get("quantity_gap", 6)))
        font_id = str(session.ui_preset.get("font_id", "pixelbet"))
        text_color = tuple(int(channel) for channel in session.ui_preset.get("choice_text_color", [238, 242, 248]))

        for element_id in (
            *self.row_icon_element_ids,
            *self.row_text_element_ids,
            *self.row_quantity_element_ids,
        ):
            self.screen_manager.remove(element_id)

        view_items = self._view_items(session)
        if not view_items:
            self.screen_manager.show_text(
                element_id=self.row_text_element_ids[0],
                text=" No items",
                x=list_x,
                y=list_y,
                layer=layer,
                color=text_color,
                font_id=font_id,
            )
            return

        window = view_items[session.scroll_offset:session.scroll_offset + visible_rows]
        for row_index, item_view in enumerate(window):
            absolute_index = session.scroll_offset + row_index
            is_selected = absolute_index == session.selected_index
            row_y = list_y + (row_index * row_height)
            prefix = ">" if is_selected else " "
            quantity_text = ""
            if int(item_view["quantity"]) > 1:
                quantity_text = f"x{int(item_view['quantity'])}"

            quantity_width = 0
            if quantity_text:
                quantity_width, _ = self.text_renderer.measure_text(quantity_text, font_id=font_id)
                self.screen_manager.show_text(
                    element_id=self.row_quantity_element_ids[row_index],
                    text=quantity_text,
                    x=list_x + list_width,
                    y=row_y,
                    layer=layer,
                    color=text_color,
                    font_id=font_id,
                    anchor="topright",
                )

            icon = item_view.get("icon")
            text_x = list_x
            if isinstance(icon, dict):
                self.screen_manager.show_image(
                    element_id=self.row_icon_element_ids[row_index],
                    asset_path=str(icon.get("path")),
                    x=list_x,
                    y=row_y,
                    frame_width=int(icon.get("frame_width", icon_size or 16)),
                    frame_height=int(icon.get("frame_height", icon_size or 16)),
                    frame=int(icon.get("frame", 0)),
                    layer=layer,
                )
                text_x += max(icon_size, int(icon.get("frame_width", icon_size or 16))) + icon_gap

            available_width = list_width - int(text_x - list_x)
            if quantity_width > 0:
                available_width -= quantity_width + quantity_gap
            item_text = self._clip_text(
                f"{prefix}{str(item_view['name'])}",
                max_width=max(1, available_width),
                font_id=font_id,
            )
            self.screen_manager.show_text(
                element_id=self.row_text_element_ids[row_index],
                text=item_text,
                x=text_x,
                y=row_y,
                layer=layer,
                color=text_color,
                font_id=font_id,
            )

    def _render_detail_panel(self, session: InventorySession, *, layer: int) -> None:
        """Render the selected-item detail area or the empty-state text."""
        item_view = self._selected_view_item(session)
        has_portrait = False
        if item_view is not None and isinstance(item_view.get("portrait"), dict):
            portrait_slot = dict(session.ui_preset.get("portrait_slot", {}))
            portrait = dict(item_view["portrait"])
            self.screen_manager.show_image(
                element_id=self.DETAIL_PORTRAIT_ELEMENT_ID,
                asset_path=str(portrait.get("path")),
                x=float(portrait_slot.get("x", 3)),
                y=float(portrait_slot.get("y", 151)),
                frame_width=int(portrait.get("frame_width", portrait_slot.get("width", 38))),
                frame_height=int(portrait.get("frame_height", portrait_slot.get("height", 38))),
                frame=int(portrait.get("frame", 0)),
                layer=layer,
            )
            has_portrait = True
        else:
            self.screen_manager.remove(self.DETAIL_PORTRAIT_ELEMENT_ID)

        text_layout = self._select_text_box(session, has_portrait=has_portrait)
        detail_text = self._detail_text(item_view)
        self.screen_manager.show_text(
            element_id=self.DETAIL_TEXT_ELEMENT_ID,
            text=detail_text,
            x=float(text_layout.get("x", 8)),
            y=float(text_layout.get("y", 154)),
            layer=layer,
            color=tuple(int(channel) for channel in session.ui_preset.get("text_color", [245, 232, 190])),
            font_id=str(session.ui_preset.get("font_id", "pixelbet")),
            max_width=int(text_layout.get("width", 240)),
        )

    def _render_action_popup(self, session: InventorySession, *, ui_layer: int, text_layer: int) -> None:
        """Render the small V1 `Use / Cancel` popup."""
        popup = dict(session.ui_preset.get("action_popup", {}))
        panel = dict(popup.get("panel", {}))
        panel_path = str(panel.get("path", "")).strip()
        if panel_path:
            self.screen_manager.show_image(
                element_id=self.ACTION_PANEL_ELEMENT_ID,
                asset_path=panel_path,
                x=float(panel.get("x", 152)),
                y=float(panel.get("y", 96)),
                layer=int(panel.get("layer", ui_layer)),
            )
        popup_x = float(popup.get("x", 160))
        popup_y = float(popup.get("y", 102))
        row_height = max(1.0, float(popup.get("row_height", 10)))
        popup_width = max(1, int(popup.get("width", 72)))
        font_id = str(session.ui_preset.get("font_id", "pixelbet"))
        text_color = tuple(int(channel) for channel in session.ui_preset.get("choice_text_color", [238, 242, 248]))
        options = ["Use", "Cancel"]
        for element_id in self.popup_option_element_ids:
            self.screen_manager.remove(element_id)
        for row_index, option_text in enumerate(options):
            prefix = ">" if row_index == session.action_index else " "
            self.screen_manager.show_text(
                element_id=self.popup_option_element_ids[row_index],
                text=self._clip_text(f"{prefix}{option_text}", max_width=popup_width, font_id=font_id),
                x=popup_x,
                y=popup_y + (row_index * row_height),
                layer=text_layer,
                color=text_color,
                font_id=font_id,
            )

    def _select_text_box(self, session: InventorySession, *, has_portrait: bool) -> dict[str, Any]:
        """Return the active detail text-box layout."""
        text = dict(session.ui_preset.get("text", {}))
        return dict(text.get("with_portrait" if has_portrait else "plain", {}))

    def _detail_text(self, item_view: dict[str, Any] | None) -> str:
        """Build the inventory detail-panel text payload."""
        if item_view is None:
            return "Inventory empty."
        quantity = int(item_view.get("quantity", 0))
        name = str(item_view.get("name", ""))
        header = f"{name} x{quantity}" if quantity > 1 else name
        description = str(item_view.get("description", "")).strip()
        if description:
            return f"{header}\n{description}"
        return header

    def _view_items(self, session: InventorySession) -> list[dict[str, Any]]:
        """Return rendered item-view records for the active inventory stacks."""
        entity = self.command_context.world.get_entity(session.entity_id)
        if entity is None or entity.inventory is None:
            return []

        result: list[dict[str, Any]] = []
        for stack in entity.inventory.stacks:
            try:
                definition = load_item_definition(self.project, stack.item_id)
                result.append(
                    {
                        "item_id": stack.item_id,
                        "name": definition.name,
                        "description": definition.description,
                        "icon": copy.deepcopy(definition.icon),
                        "portrait": copy.deepcopy(getattr(definition, "portrait", None)),
                        "quantity": int(stack.quantity),
                        "usable": bool(definition.use_commands),
                    }
                )
            except FileNotFoundError:
                result.append(
                    {
                        "item_id": stack.item_id,
                        "name": f"Missing Item ({stack.item_id})",
                        "description": "This item definition is missing.",
                        "icon": None,
                        "portrait": None,
                        "quantity": int(stack.quantity),
                        "usable": False,
                    }
                )
        return result

    def _selected_view_item(self, session: InventorySession) -> dict[str, Any] | None:
        """Return the currently selected item view when one exists."""
        view_items = self._view_items(session)
        if not view_items:
            return None
        selected_index = max(0, min(len(view_items) - 1, int(session.selected_index)))
        return view_items[selected_index]

    def _sync_selection_and_scroll(self, session: InventorySession) -> None:
        """Clamp selection and snapped scroll to the current inventory contents."""
        view_items = self._view_items(session)
        if not view_items:
            session.selected_index = 0
            session.scroll_offset = 0
            session.action_popup_open = False
            session.action_index = 0
            return

        session.selected_index = max(0, min(len(view_items) - 1, int(session.selected_index)))
        visible_rows = max(
            1,
            min(
                self.MAX_VISIBLE_ROWS,
                int(dict(session.ui_preset.get("list", {})).get("visible_rows", 4)),
            ),
        )
        if session.selected_index < session.scroll_offset:
            session.scroll_offset = session.selected_index
        elif session.selected_index >= session.scroll_offset + visible_rows:
            session.scroll_offset = session.selected_index - visible_rows + 1
        max_scroll_offset = max(0, len(view_items) - visible_rows)
        session.scroll_offset = max(0, min(max_scroll_offset, int(session.scroll_offset)))

    def _move_selection(self, session: InventorySession, *, delta: int) -> None:
        """Move the main inventory selection and rerender if it changed."""
        view_items = self._view_items(session)
        if not view_items:
            self._deny_feedback(session)
            return
        next_index = max(0, min(len(view_items) - 1, session.selected_index + int(delta)))
        if next_index == session.selected_index:
            return
        session.selected_index = next_index
        self._sync_selection_and_scroll(session)
        self._render_session(session)

    def _move_action_selection(self, session: InventorySession, *, delta: int) -> None:
        """Move the `Use / Cancel` popup selection."""
        next_index = max(0, min(1, session.action_index + int(delta)))
        if next_index == session.action_index:
            return
        session.action_index = next_index
        self._render_session(session)

    def _open_action_popup_or_deny(self, session: InventorySession) -> None:
        """Open the V1 action popup for usable items or play light deny feedback."""
        item_view = self._selected_view_item(session)
        if item_view is None or not bool(item_view.get("usable")):
            self._deny_feedback(session)
            return
        session.action_popup_open = True
        session.action_index = 0
        self._render_session(session)

    def _confirm_action_popup(self, session: InventorySession) -> None:
        """Apply the selected popup action."""
        if session.action_index == 0:
            self._confirm_use(session)
            return
        session.action_popup_open = False
        session.action_index = 0
        self._render_session(session)

    def _confirm_use(self, session: InventorySession) -> None:
        """Close inventory and queue one direct `use_inventory_item` action."""
        item_view = self._selected_view_item(session)
        if item_view is None or not bool(item_view.get("usable")):
            self._deny_feedback(session)
            return
        self.close_current_session()
        command_runner = self.command_context.command_runner
        if command_runner is None:
            raise ValueError("Inventory use requires an active command runner.")
        command_runner.enqueue(
            "use_inventory_item",
            entity_id=session.entity_id,
            item_id=str(item_view["item_id"]),
            quantity=1,
            source_entity_id=session.entity_id,
        )

    def _deny_feedback(self, session: InventorySession) -> None:
        """Play one optional small deny sound when the preset configures it."""
        audio_player = self.command_context.audio_player
        if audio_player is None:
            return
        deny_sfx_path = session.ui_preset.get("deny_sfx_path")
        if not isinstance(deny_sfx_path, str) or not deny_sfx_path.strip():
            return
        play_audio = getattr(audio_player, "play_audio", None)
        if play_audio is None:
            return
        play_audio(str(deny_sfx_path).strip())

    def _clip_text(self, text: str, *, max_width: int, font_id: str) -> str:
        """Return the longest string prefix that fits within one width budget."""
        if max_width <= 0:
            return ""
        clipped = ""
        for character in str(text):
            candidate = clipped + character
            measured_width, _ = self.text_renderer.measure_text(candidate, font_id=font_id)
            if measured_width > int(max_width):
                break
            clipped = candidate
        return clipped

    def _clear_ui(self) -> None:
        """Remove all engine-owned inventory UI elements."""
        self.screen_manager.remove(self.LIST_PANEL_ELEMENT_ID)
        self.screen_manager.remove(self.DETAIL_PANEL_ELEMENT_ID)
        self.screen_manager.remove(self.DETAIL_PORTRAIT_ELEMENT_ID)
        self.screen_manager.remove(self.DETAIL_TEXT_ELEMENT_ID)
        self.screen_manager.remove(self.ACTION_PANEL_ELEMENT_ID)
        for element_id in (
            *self.row_icon_element_ids,
            *self.row_text_element_ids,
            *self.row_quantity_element_ids,
            *self.popup_option_element_ids,
        ):
            self.screen_manager.remove(element_id)
