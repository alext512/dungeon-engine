"""Area entity list used for selecting hard-to-click instances."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from area_editor.documents.area_document import EntityDocument

_ENTITY_ID_ROLE = Qt.ItemDataRole.UserRole + 1
_PLACEHOLDER_ROLE = Qt.ItemDataRole.UserRole + 2


class AreaEntityListPanel(QWidget):
    """List entity instances for the active area and emit selection requests."""

    entity_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("AreaEntityListPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._target_label = QLabel("Area Entities: none")
        layout.addWidget(self._target_label)

        self._filter_combo = QComboBox()
        self._filter_combo.addItem("All entities", "all")
        self._filter_combo.addItem("World entities", "world")
        self._filter_combo.addItem("Screen entities", "screen")
        self._filter_combo.currentIndexChanged.connect(self._refresh_list)
        layout.addWidget(self._filter_combo)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_current_item_changed)
        layout.addWidget(self._list, 1)

        self._area_id: str | None = None
        self._entities: list[EntityDocument] = []
        self._effective_space_for: Callable[[EntityDocument], str] | None = None
        self._selected_entity_id: str | None = None

    def load_area(
        self,
        area_id: str,
        entities: list[EntityDocument],
        *,
        selected_entity_id: str | None = None,
        effective_space_for: Callable[[EntityDocument], str] | None = None,
    ) -> None:
        """Replace the list contents with the active area's entity instances."""
        self._area_id = area_id
        self._entities = list(entities)
        self._effective_space_for = effective_space_for
        self._selected_entity_id = selected_entity_id
        self._target_label.setText(f"Area Entities: {area_id}")
        self._refresh_list()

    def clear(self) -> None:
        self._area_id = None
        self._entities = []
        self._effective_space_for = None
        self._selected_entity_id = None
        self._target_label.setText("Area Entities: none")
        self._list.blockSignals(True)
        self._list.clear()
        self._list.blockSignals(False)

    def select_entity(self, entity_id: str | None) -> None:
        """Highlight an entity row without emitting another selection request."""
        self._selected_entity_id = entity_id
        self._select_visible_entity(entity_id)

    def entity_ids(self) -> list[str]:
        """Return visible, selectable entity ids in list order."""
        ids: list[str] = []
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is None or item.data(_PLACEHOLDER_ROLE):
                continue
            ids.append(str(item.data(_ENTITY_ID_ROLE) or ""))
        return ids

    def _refresh_list(self) -> None:
        current_filter = str(self._filter_combo.currentData() or "all")
        visible_entities = [
            entity
            for entity in self._entities
            if current_filter == "all" or self._effective_space(entity) == current_filter
        ]

        self._list.blockSignals(True)
        self._list.clear()
        if not visible_entities:
            item = QListWidgetItem("No entities in this view.")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            item.setData(_PLACEHOLDER_ROLE, True)
            self._list.addItem(item)
        else:
            for entity in visible_entities:
                item = QListWidgetItem(self._format_entity_label(entity))
                item.setData(_ENTITY_ID_ROLE, entity.id)
                item.setData(_PLACEHOLDER_ROLE, False)
                self._list.addItem(item)
        self._list.blockSignals(False)
        self._select_visible_entity(self._selected_entity_id)

    def _select_visible_entity(self, entity_id: str | None) -> None:
        self._list.blockSignals(True)
        try:
            self._list.clearSelection()
            if not entity_id:
                self._list.setCurrentRow(-1)
                return
            for row in range(self._list.count()):
                item = self._list.item(row)
                if item is None or item.data(_PLACEHOLDER_ROLE):
                    continue
                if item.data(_ENTITY_ID_ROLE) == entity_id:
                    self._list.setCurrentItem(item)
                    return
            self._list.setCurrentRow(-1)
        finally:
            self._list.blockSignals(False)

    def _on_current_item_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None or current.data(_PLACEHOLDER_ROLE):
            return
        entity_id = str(current.data(_ENTITY_ID_ROLE) or "")
        if not entity_id:
            return
        self._selected_entity_id = entity_id
        self.entity_selected.emit(entity_id)

    def _format_entity_label(self, entity: EntityDocument) -> str:
        template = entity.template.rsplit("/", 1)[-1] if entity.template else "entity"
        space = self._effective_space(entity)
        if space == "screen":
            location = f"screen ({entity.pixel_x or 0}, {entity.pixel_y or 0})"
        else:
            location = f"world ({entity.grid_x}, {entity.grid_y})"
        return f"{entity.id}  [{template}]  {location}"

    def _effective_space(self, entity: EntityDocument) -> str:
        if self._effective_space_for is None:
            return entity.space
        return self._effective_space_for(entity)
