from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

_ENTITY_ID_ROLE = Qt.ItemDataRole.UserRole + 1


@dataclass(slots=True)
class EntityStackPickerEntry:
    entity_id: str
    label: str


class EntityStackPickerPopup(QFrame):
    """Small popup list for choosing one entity from stacked overlaps."""

    entity_chosen = Signal(str, str, str)  # area_id, entity_id, purpose

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("EntityStackPickerPopup")
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self._title_label = QLabel("Choose Entity")
        layout.addWidget(self._title_label)

        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_item_chosen)
        self._list.itemActivated.connect(self._on_item_chosen)
        layout.addWidget(self._list)

        self._target_area_id: str | None = None
        self._purpose: str = "select"

    @property
    def target_area_id(self) -> str | None:
        return self._target_area_id

    @property
    def purpose(self) -> str:
        return self._purpose

    def entity_ids(self) -> list[str]:
        ids: list[str] = []
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is None:
                continue
            entity_id = str(item.data(_ENTITY_ID_ROLE) or "")
            if entity_id:
                ids.append(entity_id)
        return ids

    def show_entries(
        self,
        *,
        area_id: str,
        purpose: str,
        entries: list[EntityStackPickerEntry],
        global_pos: QPoint,
    ) -> bool:
        if not entries:
            self.hide()
            return False

        self._target_area_id = area_id
        self._purpose = purpose
        self._title_label.setText(
            "Delete Which Entity?"
            if purpose == "delete"
            else "Choose Entity"
        )

        self._list.clear()
        for entry in entries:
            item = QListWidgetItem(entry.label)
            item.setData(_ENTITY_ID_ROLE, entry.entity_id)
            self._list.addItem(item)
        self._list.setCurrentRow(0)

        self.adjustSize()
        self.move(global_pos + QPoint(12, 12))
        self.show()
        self.raise_()
        self.activateWindow()
        self._list.setFocus()
        return True

    def choose_entity(self, entity_id: str) -> bool:
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is None:
                continue
            if item.data(_ENTITY_ID_ROLE) == entity_id:
                self._emit_choice(entity_id)
                return True
        return False

    def _on_item_chosen(self, item: QListWidgetItem) -> None:
        entity_id = str(item.data(_ENTITY_ID_ROLE) or "")
        if entity_id:
            self._emit_choice(entity_id)

    def _emit_choice(self, entity_id: str) -> None:
        area_id = self._target_area_id
        if not area_id:
            return
        self.hide()
        self.entity_chosen.emit(area_id, entity_id, self._purpose)
