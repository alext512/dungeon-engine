from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class _TilesetDetailsDialog(QDialog):
    """Small dialog for adding or re-slicing a tileset."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        path_value: str,
        tile_width: int,
        tile_height: int,
        allow_path_edit: bool,
        browse_callback: Callable[[], str | None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tileset Details")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._path_edit = QLineEdit(path_value)
        self._path_edit.setReadOnly(not allow_path_edit)
        path_row = QHBoxLayout()
        path_row.addWidget(self._path_edit, 1)
        if allow_path_edit:
            browse_button = QPushButton("Browse...")
            browse_button.clicked.connect(lambda: self._browse_for_path(browse_callback))
            path_row.addWidget(browse_button)
        form.addRow("Path", self._wrap_layout(path_row))

        self._tile_width = QSpinBox()
        self._tile_width.setRange(1, 4096)
        self._tile_width.setValue(tile_width)
        form.addRow("Tile width", self._tile_width)

        self._tile_height = QSpinBox()
        self._tile_height.setRange(1, 4096)
        self._tile_height.setValue(tile_height)
        form.addRow("Tile height", self._tile_height)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _wrap_layout(inner: QHBoxLayout) -> QWidget:
        wrapper = QWidget()
        wrapper.setLayout(inner)
        return wrapper

    def _browse_for_path(self, callback: Callable[[], str | None] | None) -> None:
        if callback is None:
            return
        selected = callback()
        if selected:
            self._path_edit.setText(selected)

    @property
    def authored_path(self) -> str:
        return self._path_edit.text().strip()

    @property
    def tile_width(self) -> int:
        return self._tile_width.value()

    @property
    def tile_height(self) -> int:
        return self._tile_height.value()


class _NewAreaDialog(QDialog):
    """Small dialog for creating one new area file."""

    def __init__(self, parent: QWidget | None, *, tile_size: int = 16) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Area")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._area_id = QLineEdit()
        form.addRow("Area ID", self._area_id)

        self._width = QSpinBox()
        self._width.setRange(1, 9999)
        self._width.setValue(20)
        form.addRow("Width", self._width)

        self._height = QSpinBox()
        self._height.setRange(1, 9999)
        self._height.setValue(15)
        form.addRow("Height", self._height)

        self._tile_size = QSpinBox()
        self._tile_size.setRange(1, 4096)
        self._tile_size.setValue(max(1, int(tile_size)))
        form.addRow("Tile Size", self._tile_size)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def area_id(self) -> str:
        return self._area_id.text().strip()

    @property
    def width(self) -> int:
        return self._width.value()

    @property
    def height(self) -> int:
        return self._height.value()

    @property
    def tile_size(self) -> int:
        return self._tile_size.value()


class _AreaCountDialog(QDialog):
    """Small dialog for adding/removing rows or columns."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        title: str,
        label: str,
        minimum: int = 1,
        maximum: int = 9999,
        value: int = 1,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(label))

        self._count = QSpinBox()
        self._count.setRange(minimum, maximum)
        self._count.setValue(value)
        layout.addWidget(self._count)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def count(self) -> int:
        return self._count.value()
