"""Dialog for choosing an entity id from project-discovered entities."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


GLOBAL_AREA_KEY = "__global__"

_ENTITY_ID_ROLE = Qt.ItemDataRole.UserRole + 1
_AREA_KEY_ROLE = Qt.ItemDataRole.UserRole + 2
_PLACEHOLDER_ROLE = Qt.ItemDataRole.UserRole + 3


@dataclass(frozen=True)
class EntityReferencePickerEntry:
    entity_id: str
    template_id: str | None
    area_key: str
    area_label: str
    scope: str
    space: str
    position_text: str

    def matches_filter(self, text: str) -> bool:
        lowered = text.strip().lower()
        if not lowered:
            return True
        haystacks = (
            self.entity_id,
            self.template_id or "",
            self.area_label,
            self.scope,
            self.space,
            self.position_text,
        )
        return any(lowered in value.lower() for value in haystacks)

    def display_text(self) -> str:
        template = self.template_id.rsplit("/", 1)[-1] if self.template_id else "entity"
        return f"{self.entity_id}  [{template}]  {self.position_text}"

    def tool_tip(self) -> str:
        lines = [self.entity_id]
        if self.template_id:
            lines.append(self.template_id)
        lines.append(f"{self.scope} / {self.space}")
        lines.append(self.position_text)
        if self.area_key != GLOBAL_AREA_KEY:
            lines.append(self.area_label)
        return "\n".join(lines)


class EntityReferencePickerDialog(QDialog):
    """Browse known entities by area, scope, and free-text filter."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose Entity")
        self.resize(520, 420)

        layout = QVBoxLayout(self)

        area_row = QHBoxLayout()
        area_row.addWidget(QLabel("Area"))
        self._area_combo = QComboBox()
        self._area_combo.currentIndexChanged.connect(self._refresh_list)
        area_row.addWidget(self._area_combo, 1)
        layout.addLayout(area_row)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter"))
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Search id, template, space, or position")
        self._filter_edit.textChanged.connect(self._refresh_list)
        filter_row.addWidget(self._filter_edit, 1)
        layout.addLayout(filter_row)

        self._missing_value_label = QLabel("")
        self._missing_value_label.setWordWrap(True)
        self._missing_value_label.setStyleSheet("color: #a25b00;")
        self._missing_value_label.hide()
        layout.addWidget(self._missing_value_label)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list.currentItemChanged.connect(self._on_current_item_changed)
        layout.addWidget(self._list, 1)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

        self._entries: list[EntityReferencePickerEntry] = []
        self._current_value = ""
        self._locked_area_key: str | None = None
        self._ok_button = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
        if self._ok_button is not None:
            self._ok_button.setEnabled(False)

    @property
    def selected_entity_id(self) -> str | None:
        item = self._list.currentItem()
        if item is None or item.data(_PLACEHOLDER_ROLE):
            return None
        entity_id = str(item.data(_ENTITY_ID_ROLE) or "").strip()
        return entity_id or None

    def current_area_key(self) -> str | None:
        area_key = self._area_combo.currentData()
        if area_key in (None, ""):
            return None
        return str(area_key)

    def area_selection_enabled(self) -> bool:
        return self._area_combo.isEnabled()

    def area_keys(self) -> list[str]:
        keys: list[str] = []
        for index in range(self._area_combo.count()):
            area_key = self._area_combo.itemData(index)
            if area_key not in (None, ""):
                keys.append(str(area_key))
        return keys

    def visible_entity_ids(self) -> list[str]:
        ids: list[str] = []
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is None or item.data(_PLACEHOLDER_ROLE):
                continue
            entity_id = str(item.data(_ENTITY_ID_ROLE) or "").strip()
            if entity_id:
                ids.append(entity_id)
        return ids

    def missing_value_text(self) -> str:
        return self._missing_value_label.text()

    def set_entries(
        self,
        entries: list[EntityReferencePickerEntry],
        *,
        current_value: str = "",
        preferred_area_key: str | None = None,
        locked_area_key: str | None = None,
    ) -> None:
        self._entries = list(entries)
        self._current_value = current_value.strip()
        self._locked_area_key = str(locked_area_key or "").strip() or None

        available_areas: dict[str, str] = {}
        for entry in self._entries:
            available_areas.setdefault(entry.area_key, entry.area_label)

        self._area_combo.blockSignals(True)
        try:
            self._area_combo.clear()
            for area_key, area_label in sorted(
                available_areas.items(),
                key=lambda pair: (
                    pair[0] == GLOBAL_AREA_KEY,
                    pair[1].lower(),
                ),
            ):
                self._area_combo.addItem(area_label, area_key)
        finally:
            self._area_combo.blockSignals(False)
        self._area_combo.setEnabled(self._locked_area_key is None)

        chosen_area_key = self._resolve_initial_area_key(
            self._locked_area_key or preferred_area_key
        )
        if chosen_area_key is not None:
            self.select_area_key(chosen_area_key)
        self._refresh_list()

    def select_area_key(self, area_key: str) -> bool:
        for index in range(self._area_combo.count()):
            if self._area_combo.itemData(index) == area_key:
                self._area_combo.setCurrentIndex(index)
                return True
        return False

    def set_filter_text(self, text: str) -> None:
        self._filter_edit.setText(text)

    def choose_entity(self, entity_id: str) -> bool:
        normalized = str(entity_id).strip()
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is None or item.data(_PLACEHOLDER_ROLE):
                continue
            if str(item.data(_ENTITY_ID_ROLE) or "").strip() == normalized:
                self._list.setCurrentItem(item)
                return True
        return False

    def _resolve_initial_area_key(self, preferred_area_key: str | None) -> str | None:
        preferred = str(preferred_area_key or "").strip()
        current = self._current_value

        if current:
            for entry in self._entries:
                if entry.entity_id == current:
                    return entry.area_key

        if preferred and preferred in self.area_keys():
            return preferred

        if self._area_combo.count() == 0:
            return None
        area_key = self._area_combo.itemData(0)
        if area_key in (None, ""):
            return None
        return str(area_key)

    def _refresh_list(self) -> None:
        area_key = self.current_area_key()
        filter_text = self._filter_edit.text()
        visible_entries = [
            entry
            for entry in self._entries
            if (area_key is None or entry.area_key == area_key)
            and entry.matches_filter(filter_text)
        ]

        self._list.blockSignals(True)
        try:
            self._list.clear()
            if not visible_entries:
                item = QListWidgetItem("No entities match this view.")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                item.setData(_PLACEHOLDER_ROLE, True)
                self._list.addItem(item)
            else:
                for entry in visible_entries:
                    item = QListWidgetItem(entry.display_text())
                    item.setToolTip(entry.tool_tip())
                    item.setData(_ENTITY_ID_ROLE, entry.entity_id)
                    item.setData(_AREA_KEY_ROLE, entry.area_key)
                    item.setData(_PLACEHOLDER_ROLE, False)
                    self._list.addItem(item)
        finally:
            self._list.blockSignals(False)

        self._sync_missing_value_label(visible_entries)
        if self._current_value and not self.choose_entity(self._current_value):
            if self._list.count() > 0:
                self._list.setCurrentRow(0)
        elif not self._current_value and self._list.count() > 0:
            self._list.setCurrentRow(0)
        self._sync_ok_button()

    def _sync_missing_value_label(
        self,
        visible_entries: list[EntityReferencePickerEntry],
    ) -> None:
        current = self._current_value
        if not current:
            self._missing_value_label.hide()
            return

        if any(entry.entity_id == current for entry in self._entries):
            if any(entry.entity_id == current for entry in visible_entries):
                self._missing_value_label.hide()
                return
            self._missing_value_label.setText(
                f"Current value '{current}' is outside the current area/filter."
            )
            self._missing_value_label.show()
            return

        self._missing_value_label.setText(
            f"Current value '{current}' was not found in this project."
        )
        self._missing_value_label.show()

    def _sync_ok_button(self) -> None:
        if self._ok_button is None:
            return
        self._ok_button.setEnabled(self.selected_entity_id is not None)

    def _on_current_item_changed(self, _current, _previous) -> None:
        self._sync_ok_button()

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        if item.data(_PLACEHOLDER_ROLE):
            return
        self._list.setCurrentItem(item)
        self.accept()
