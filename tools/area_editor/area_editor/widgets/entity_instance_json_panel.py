"""Dockable entity-instance editor with JSON and structured field tabs."""

from __future__ import annotations

import json
import re

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from area_editor.catalogs.template_catalog import TemplateCatalog
from area_editor.documents.area_document import EntityDocument

_JSON_NUMBER_RE = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?\Z")


def _section_label(text: str) -> QLabel:
    label = QLabel(text)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


def _set_row_visible(label: QWidget, field: QWidget, visible: bool) -> None:
    label.setVisible(visible)
    field.setVisible(visible)


def _parse_parameter_text(text: str):
    stripped = text.strip()
    if not stripped:
        return None, False
    if stripped[0] in "[{":
        try:
            return json.loads(stripped), True
        except json.JSONDecodeError:
            return text, True
    if stripped in {"true", "false", "null"} or _JSON_NUMBER_RE.fullmatch(stripped):
        try:
            return json.loads(stripped), True
        except json.JSONDecodeError:
            return text, True
    return text, True


class _EntityInstanceJsonEditor(QWidget):
    """Shows one selected entity instance as editable JSON."""

    apply_requested = Signal()
    revert_requested = Signal()
    dirty_changed = Signal(bool)
    editing_enabled_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._target_label = QLabel("Selected Entity: None")
        layout.addWidget(self._target_label)

        self._editor = QPlainTextEdit()
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._editor.setFont(font)
        self._editor.setReadOnly(True)
        self._editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._editor, 1)

        buttons = QHBoxLayout()
        self._apply_button = QPushButton("Apply")
        self._apply_button.clicked.connect(self.apply_requested.emit)
        buttons.addWidget(self._apply_button)
        self._revert_button = QPushButton("Revert")
        self._revert_button.clicked.connect(self.revert_requested.emit)
        buttons.addWidget(self._revert_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._entity_id: str | None = None
        self._editing_enabled = False
        self._dirty = False
        self._loading = False
        self._set_buttons_enabled(False)

    @property
    def entity_id(self) -> str | None:
        return self._entity_id

    @property
    def editing_enabled(self) -> bool:
        return self._editing_enabled

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    @property
    def json_text(self) -> str:
        return self._editor.toPlainText()

    @property
    def editor(self) -> QPlainTextEdit:
        return self._editor

    def set_editing_enabled(self, enabled: bool) -> None:
        self._editing_enabled = enabled and self._entity_id is not None
        self._editor.setReadOnly(not self._editing_enabled)
        self._set_buttons_enabled(self._entity_id is not None)
        self.editing_enabled_changed.emit(self._editing_enabled)

    def clear_entity(self) -> None:
        self._entity_id = None
        self._editing_enabled = False
        self._loading = True
        try:
            self._editor.setPlainText("")
        finally:
            self._loading = False
        self._target_label.setText("Selected Entity: None")
        self._set_dirty(False)
        self._editor.setReadOnly(True)
        self._set_buttons_enabled(False)

    def load_entity(self, entity: EntityDocument) -> None:
        self._entity_id = entity.id
        text = json.dumps(entity.to_dict(), indent=2, ensure_ascii=False)
        self._loading = True
        try:
            self._editor.setPlainText(text)
        finally:
            self._loading = False
        self._target_label.setText(f"Selected Entity: {entity.id}")
        self._set_dirty(False)
        self._editor.setReadOnly(not self._editing_enabled)
        self._set_buttons_enabled(True)

    def set_json_text(self, text: str) -> None:
        self._loading = True
        try:
            self._editor.setPlainText(text)
        finally:
            self._loading = False
        self._set_dirty(False)

    def _on_text_changed(self) -> None:
        if self._loading or not self._editing_enabled:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirty_changed.emit(dirty)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self._apply_button.setEnabled(enabled)
        self._revert_button.setEnabled(enabled)


class _EntityInstanceFieldsEditor(QWidget):
    """Structured editor for high-value entity instance fields."""

    apply_requested = Signal()
    revert_requested = Signal()
    dirty_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        self._target_label = QLabel("Selected Entity: None")
        outer.addWidget(self._target_label)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        outer.addWidget(self._scroll, 1)

        container = QWidget()
        self._form = QFormLayout(container)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._scroll.setWidget(container)

        self._form.addRow(_section_label("Identity"))
        self._id_label = QLabel("id")
        self._id_edit = QLineEdit()
        self._form.addRow(self._id_label, self._id_edit)

        self._template_label_title = QLabel("template")
        self._template_label = QLineEdit()
        self._template_label.setReadOnly(True)
        self._template_label.setText("-")
        self._form.addRow(self._template_label_title, self._template_label)

        self._form.addRow(_section_label("Position"))
        self._space_label_title = QLabel("space")
        self._space_label = QLabel("world")
        self._form.addRow(self._space_label_title, self._space_label)

        self._x_label = QLabel("grid_x")
        self._x_spin = QSpinBox()
        self._x_spin.setRange(0, 0)
        self._form.addRow(self._x_label, self._x_spin)

        self._y_label = QLabel("grid_y")
        self._y_spin = QSpinBox()
        self._y_spin.setRange(0, 0)
        self._form.addRow(self._y_label, self._y_spin)

        self._pixel_x_label = QLabel("pixel_x")
        self._pixel_x_row = QWidget()
        self._pixel_x_check = QCheckBox("Use pixel offset")
        self._pixel_x_spin = QSpinBox()
        self._pixel_x_spin.setRange(-999999, 999999)
        pixel_x_layout = QHBoxLayout(self._pixel_x_row)
        pixel_x_layout.setContentsMargins(0, 0, 0, 0)
        pixel_x_layout.addWidget(self._pixel_x_check)
        pixel_x_layout.addWidget(self._pixel_x_spin, 1)
        self._form.addRow(self._pixel_x_label, self._pixel_x_row)

        self._pixel_y_label = QLabel("pixel_y")
        self._pixel_y_row = QWidget()
        self._pixel_y_check = QCheckBox("Use pixel offset")
        self._pixel_y_spin = QSpinBox()
        self._pixel_y_spin.setRange(-999999, 999999)
        pixel_y_layout = QHBoxLayout(self._pixel_y_row)
        pixel_y_layout.setContentsMargins(0, 0, 0, 0)
        pixel_y_layout.addWidget(self._pixel_y_check)
        pixel_y_layout.addWidget(self._pixel_y_spin, 1)
        self._form.addRow(self._pixel_y_label, self._pixel_y_row)

        self._render_note = QLabel("Render properties are in the Render Properties panel ->")
        self._render_note.setStyleSheet("color: #666; font-style: italic;")
        self._render_note.setWordWrap(True)
        self._form.addRow(self._render_note)

        self._form.addRow(_section_label("Parameters"))
        self._parameter_warning = QLabel("")
        self._parameter_warning.setWordWrap(True)
        self._parameter_warning.setStyleSheet("color: #a25b00;")
        self._parameter_warning.hide()
        self._form.addRow(self._parameter_warning)

        self._parameters_widget = QWidget()
        self._parameters_layout = QFormLayout(self._parameters_widget)
        self._parameters_layout.setContentsMargins(0, 0, 0, 0)
        self._parameters_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        self._form.addRow(self._parameters_widget)

        self._form.addRow(_section_label("Extra"))
        self._extra_label = QLabel("extra")
        self._extra_text = QPlainTextEdit()
        self._extra_text.setReadOnly(True)
        self._extra_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        extra_font = QFont("Consolas", 10)
        extra_font.setStyleHint(QFont.StyleHint.Monospace)
        self._extra_text.setFont(extra_font)
        self._extra_text.setMaximumBlockCount(0)
        self._extra_text.setFixedHeight(120)
        self._form.addRow(self._extra_label, self._extra_text)

        buttons = QHBoxLayout()
        self._apply_button = QPushButton("Apply")
        self._apply_button.clicked.connect(self.apply_requested.emit)
        buttons.addWidget(self._apply_button)
        self._revert_button = QPushButton("Revert")
        self._revert_button.clicked.connect(self.revert_requested.emit)
        buttons.addWidget(self._revert_button)
        buttons.addStretch(1)
        outer.addLayout(buttons)

        self._template_catalog: TemplateCatalog | None = None
        self._entity: EntityDocument | None = None
        self._effective_space = "world"
        self._loading = False
        self._dirty = False
        self._area_width = 0
        self._area_height = 0
        self._parameter_edits: dict[str, QLineEdit] = {}
        self._parameters_editable = True

        self._id_edit.textChanged.connect(self._on_field_changed)
        self._x_spin.valueChanged.connect(self._on_field_changed)
        self._y_spin.valueChanged.connect(self._on_field_changed)
        self._pixel_x_check.toggled.connect(self._on_pixel_check_toggled)
        self._pixel_y_check.toggled.connect(self._on_pixel_check_toggled)
        self._pixel_x_spin.valueChanged.connect(self._on_field_changed)
        self._pixel_y_spin.valueChanged.connect(self._on_field_changed)

        self._set_buttons_enabled(False)
        self._clear_parameter_rows()
        self._set_extra_visible(False)
        self._sync_pixel_spin_enabled()

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def set_template_catalog(self, catalog: TemplateCatalog | None) -> None:
        self._template_catalog = catalog

    def set_area_bounds(self, width: int, height: int) -> None:
        self._area_width = max(0, width)
        self._area_height = max(0, height)
        max_x = max(0, self._area_width - 1)
        max_y = max(0, self._area_height - 1)
        blockers = [QSignalBlocker(self._x_spin), QSignalBlocker(self._y_spin)]
        self._x_spin.setRange(0, max_x)
        self._y_spin.setRange(0, max_y)
        del blockers

    def clear_entity(self) -> None:
        self._entity = None
        self._effective_space = "world"
        self._loading = True
        try:
            blockers = [
                QSignalBlocker(self._id_edit),
                QSignalBlocker(self._x_spin),
                QSignalBlocker(self._y_spin),
                QSignalBlocker(self._pixel_x_check),
                QSignalBlocker(self._pixel_y_check),
                QSignalBlocker(self._pixel_x_spin),
                QSignalBlocker(self._pixel_y_spin),
            ]
            self._id_edit.clear()
            self._template_label.setText("-")
            self._space_label.setText("world")
            self._x_spin.setValue(0)
            self._y_spin.setValue(0)
            self._pixel_x_check.setChecked(False)
            self._pixel_y_check.setChecked(False)
            self._pixel_x_spin.setValue(0)
            self._pixel_y_spin.setValue(0)
            del blockers
        finally:
            self._loading = False
        self._target_label.setText("Selected Entity: None")
        self._clear_parameter_rows()
        self._parameter_warning.hide()
        self._parameters_widget.show()
        self._parameters_editable = True
        self._set_extra_visible(False)
        self._apply_space_visibility(has_pixel_x=False, has_pixel_y=False)
        self._sync_pixel_spin_enabled()
        self._set_dirty(False)
        self._set_buttons_enabled(False)

    def load_entity(self, entity: EntityDocument) -> None:
        self._entity = entity
        self._effective_space = self._compute_effective_space(entity)
        has_pixel_x = entity.pixel_x is not None
        has_pixel_y = entity.pixel_y is not None
        self._loading = True
        try:
            blockers = [
                QSignalBlocker(self._id_edit),
                QSignalBlocker(self._x_spin),
                QSignalBlocker(self._y_spin),
                QSignalBlocker(self._pixel_x_check),
                QSignalBlocker(self._pixel_y_check),
                QSignalBlocker(self._pixel_x_spin),
                QSignalBlocker(self._pixel_y_spin),
            ]
            self._id_edit.setText(entity.id)
            self._template_label.setText(entity.template or "-")
            self._template_label.setCursorPosition(0)
            self._space_label.setText(self._effective_space)
            self._x_spin.setValue(entity.x)
            self._y_spin.setValue(entity.y)
            self._pixel_x_check.setChecked(has_pixel_x)
            self._pixel_y_check.setChecked(has_pixel_y)
            self._pixel_x_spin.setValue(entity.pixel_x or 0)
            self._pixel_y_spin.setValue(entity.pixel_y or 0)
            del blockers
        finally:
            self._loading = False
        self._target_label.setText(f"Selected Entity: {entity.id}")
        self._apply_space_visibility(has_pixel_x=has_pixel_x, has_pixel_y=has_pixel_y)
        self._sync_pixel_spin_enabled()
        self._rebuild_parameter_rows(entity)
        if entity._extra:
            self._extra_text.setPlainText(
                json.dumps(entity._extra, indent=2, ensure_ascii=False)
            )
            self._set_extra_visible(True)
        else:
            self._set_extra_visible(False)
        self._set_dirty(False)
        self._set_buttons_enabled(True)

    def build_entity_document(self) -> EntityDocument:
        if self._entity is None:
            raise RuntimeError("No entity is currently loaded.")

        parameters = self._build_parameters_value()
        if self._effective_space == "screen":
            space = "screen"
            grid_x = self._entity.grid_x
            grid_y = self._entity.grid_y
            pixel_x = self._pixel_x_spin.value()
            pixel_y = self._pixel_y_spin.value()
        else:
            space = self._entity.space
            grid_x = self._x_spin.value()
            grid_y = self._y_spin.value()
            pixel_x = self._pixel_x_spin.value() if self._pixel_x_check.isChecked() else None
            pixel_y = self._pixel_y_spin.value() if self._pixel_y_check.isChecked() else None

        return EntityDocument(
            id=self._id_edit.text().strip(),
            grid_x=grid_x,
            grid_y=grid_y,
            pixel_x=pixel_x,
            pixel_y=pixel_y,
            space=space,
            template=self._entity.template,
            parameters=parameters,
            _extra=dict(self._entity._extra),
        )

    def _compute_effective_space(self, entity: EntityDocument) -> str:
        effective_space = entity.space
        if (
            effective_space == "world"
            and entity.template
            and self._template_catalog is not None
        ):
            template_space = self._template_catalog.get_template_space(entity.template)
            if template_space is not None:
                effective_space = template_space
        return effective_space

    def _apply_space_visibility(self, *, has_pixel_x: bool, has_pixel_y: bool) -> None:
        is_screen = self._effective_space == "screen"
        _set_row_visible(self._x_label, self._x_spin, not is_screen)
        _set_row_visible(self._y_label, self._y_spin, not is_screen)

        pixel_rows_visible = is_screen or has_pixel_x or has_pixel_y
        _set_row_visible(self._pixel_x_label, self._pixel_x_row, pixel_rows_visible)
        _set_row_visible(self._pixel_y_label, self._pixel_y_row, pixel_rows_visible)

        self._pixel_x_check.setVisible(not is_screen)
        self._pixel_y_check.setVisible(not is_screen)
        if is_screen:
            blockers = [QSignalBlocker(self._pixel_x_check), QSignalBlocker(self._pixel_y_check)]
            self._pixel_x_check.setChecked(True)
            self._pixel_y_check.setChecked(True)
            del blockers

    def _rebuild_parameter_rows(self, entity: EntityDocument) -> None:
        self._clear_parameter_rows()
        parameters = entity.parameters
        if parameters is not None and not isinstance(parameters, dict):
            self._parameters_editable = False
            self._parameters_widget.hide()
            self._parameter_warning.setText(
                "Parameters are not a JSON object for this entity. "
                "Use the JSON tab to edit them."
            )
            self._parameter_warning.show()
            return

        self._parameters_editable = True
        self._parameters_widget.show()
        self._parameter_warning.hide()
        parameter_names: set[str] = set()
        if entity.template and self._template_catalog is not None:
            parameter_names.update(
                self._template_catalog.get_template_parameter_names(entity.template)
            )
        if isinstance(parameters, dict):
            parameter_names.update(parameters.keys())

        for name in sorted(parameter_names):
            label = QLabel(name)
            edit = QLineEdit()
            value = None if not isinstance(parameters, dict) else parameters.get(name)
            if value is None:
                edit.setText("")
            elif isinstance(value, str):
                edit.setText(value)
            else:
                edit.setText(json.dumps(value, ensure_ascii=False))
            edit.textChanged.connect(self._on_field_changed)
            self._parameters_layout.addRow(label, edit)
            self._parameter_edits[name] = edit

    def _clear_parameter_rows(self) -> None:
        self._parameter_edits.clear()
        while self._parameters_layout.rowCount() > 0:
            self._parameters_layout.removeRow(0)

    def _build_parameters_value(self):
        if self._entity is None:
            return None
        if not self._parameters_editable:
            return self._entity.parameters
        parameters: dict[str, object] = {}
        for name, edit in self._parameter_edits.items():
            value, keep = _parse_parameter_text(edit.text())
            if not keep:
                continue
            parameters[name] = value
        return parameters or None

    def _set_extra_visible(self, visible: bool) -> None:
        _set_row_visible(self._extra_label, self._extra_text, visible)
        if not visible:
            self._extra_text.clear()

    def _on_pixel_check_toggled(self) -> None:
        if self._loading:
            return
        self._sync_pixel_spin_enabled()
        self._set_dirty(True)

    def _sync_pixel_spin_enabled(self) -> None:
        screen_space = self._effective_space == "screen"
        self._pixel_x_spin.setEnabled(screen_space or self._pixel_x_check.isChecked())
        self._pixel_y_spin.setEnabled(screen_space or self._pixel_y_check.isChecked())

    def _on_field_changed(self, *_args) -> None:
        if self._loading:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirty_changed.emit(dirty)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self._apply_button.setEnabled(enabled)
        self._revert_button.setEnabled(enabled)


class EntityInstanceJsonPanel(QDockWidget):
    """Dockable entity-instance editor with internal tabs."""

    apply_requested = Signal()
    revert_requested = Signal()
    dirty_changed = Signal(bool)
    editing_enabled_changed = Signal(bool)
    fields_apply_requested = Signal()
    fields_revert_requested = Signal()
    fields_dirty_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__("Entity Instance", parent)
        self.setObjectName("EntityInstanceJsonPanel")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._json_editor = _EntityInstanceJsonEditor()
        self._fields_editor = _EntityInstanceFieldsEditor()

        self._tabs.addTab(self._json_editor, "Entity Instance JSON")
        self._tabs.addTab(self._fields_editor, "Entity Instance Editor")
        self.setWidget(self._tabs)
        self.setMinimumWidth(300)
        self._editor = self._json_editor.editor

        self._json_editor.apply_requested.connect(self.apply_requested.emit)
        self._json_editor.revert_requested.connect(self.revert_requested.emit)
        self._json_editor.dirty_changed.connect(self._on_json_dirty_changed)
        self._json_editor.editing_enabled_changed.connect(
            self.editing_enabled_changed.emit
        )
        self._fields_editor.apply_requested.connect(self.fields_apply_requested.emit)
        self._fields_editor.revert_requested.connect(self.fields_revert_requested.emit)
        self._fields_editor.dirty_changed.connect(self._on_fields_dirty_changed)
        self._sync_editor_lock_state()

    @property
    def entity_id(self) -> str | None:
        return self._json_editor.entity_id

    @property
    def editing_enabled(self) -> bool:
        return self._json_editor.editing_enabled

    @property
    def is_dirty(self) -> bool:
        return self._json_editor.is_dirty

    @property
    def fields_dirty(self) -> bool:
        return self._fields_editor.is_dirty

    @property
    def json_text(self) -> str:
        return self._json_editor.json_text

    @property
    def editor(self) -> QPlainTextEdit:
        return self._json_editor.editor

    @property
    def tab_count(self) -> int:
        return self._tabs.count()

    def tab_titles(self) -> list[str]:
        return [self._tabs.tabText(index) for index in range(self._tabs.count())]

    def set_editing_enabled(self, enabled: bool) -> None:
        self._json_editor.set_editing_enabled(enabled)
        self._sync_editor_lock_state()

    def set_template_catalog(self, catalog: TemplateCatalog | None) -> None:
        self._fields_editor.set_template_catalog(catalog)

    def set_area_bounds(self, width: int, height: int) -> None:
        self._fields_editor.set_area_bounds(width, height)

    def clear_entity(self) -> None:
        self._json_editor.clear_entity()
        self._fields_editor.clear_entity()
        self._sync_editor_lock_state()

    def load_entity(self, entity: EntityDocument) -> None:
        self._json_editor.load_entity(entity)
        self._fields_editor.load_entity(entity)
        self._sync_editor_lock_state()

    def set_json_text(self, text: str) -> None:
        self._json_editor.set_json_text(text)
        self._sync_editor_lock_state()

    def build_entity_from_fields(self) -> EntityDocument:
        return self._fields_editor.build_entity_document()

    def _on_json_dirty_changed(self, dirty: bool) -> None:
        self._sync_editor_lock_state()
        self.dirty_changed.emit(dirty)

    def _on_fields_dirty_changed(self, dirty: bool) -> None:
        self._sync_editor_lock_state()
        self.fields_dirty_changed.emit(dirty)

    def _sync_editor_lock_state(self) -> None:
        self._json_editor.setEnabled(not self._fields_editor.is_dirty)
        self._fields_editor.setEnabled(not self._json_editor.is_dirty)
