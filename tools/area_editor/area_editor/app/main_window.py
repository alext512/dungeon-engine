"""Main application window.

Hosts a tabbed document area as the central widget and docks content
browser panels on the left and the layer panel on the right.  Wires
menus, status bar, and cross-widget signals.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from area_editor.catalogs.template_catalog import TemplateCatalog
from area_editor.catalogs.tileset_catalog import TilesetCatalog
from area_editor.documents.area_document import (
    AreaDocument,
    EntityDocument,
    load_area_document,
    save_area_document,
)
from area_editor.project_io.asset_resolver import AssetResolver
from area_editor.project_io.manifest import (
    AREA_ID_PREFIX,
    ProjectManifest,
    discover_areas,
    discover_global_entities,
    load_manifest,
)
from area_editor.operations.areas import (
    add_columns_left,
    add_columns_right,
    add_rows_above,
    add_rows_below,
    can_remove_bottom_rows,
    can_remove_left_columns,
    can_remove_right_columns,
    can_remove_top_rows,
    make_empty_area_document,
    remove_bottom_rows,
    remove_left_columns,
    remove_right_columns,
    remove_top_rows,
)
from area_editor.operations.tilesets import (
    append_tileset,
    update_tileset_dimensions,
)
from area_editor.operations.entities import (
    delete_entity_by_id,
    entity_by_id,
    move_entity_by_id,
    move_entity_pixels,
    place_entity,
    place_screen_entity,
)
from area_editor.widgets.area_list_panel import AreaListPanel
from area_editor.widgets.document_tab_widget import ContentType, DocumentTabWidget
from area_editor.widgets.entity_instance_json_panel import EntityInstanceJsonPanel
from area_editor.widgets.entity_template_editor_widget import EntityTemplateEditorWidget
from area_editor.widgets.file_tree_panel import FileTreePanel
from area_editor.widgets.global_entities_editor_widget import GlobalEntitiesEditorWidget
from area_editor.widgets.global_entities_panel import GlobalEntitiesPanel
from area_editor.widgets.item_editor_widget import ItemEditorWidget
from area_editor.widgets.json_viewer_widget import JsonViewerWidget
from area_editor.widgets.layer_list_panel import LayerListPanel
from area_editor.widgets.render_properties_panel import RenderPropertiesPanel
from area_editor.widgets.template_list_panel import TemplateListPanel
from area_editor.widgets.tile_canvas import BrushType, TileCanvas
from area_editor.widgets.tileset_browser_panel import TilesetBrowserPanel

_SETTINGS_KEY_LAST_PROJECT = "last_project_path"
_SETTINGS_KEY_JSON_EDITING_ENABLED = "json_editing_enabled"
_IMAGE_SUFFIXES = {".png", ".webp", ".bmp", ".jpg", ".jpeg"}

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _EntityIdUsage:
    entity_id: str
    kind: str
    area_id: str | None = None
    file_path: Path | None = None


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

        self._display_name = QLineEdit()
        form.addRow("Display Name", self._display_name)

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
    def display_name(self) -> str:
        return self._display_name.text().strip()

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
    """Simple count dialog for directional area geometry actions."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        title: str,
        label: str,
        warning_text: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._count = QSpinBox()
        self._count.setRange(1, 9999)
        self._count.setValue(1)
        form.addRow(label, self._count)
        layout.addLayout(form)

        if warning_text:
            warning = QLabel(warning_text)
            warning.setWordWrap(True)
            warning.setStyleSheet("color: #666;")
            layout.addWidget(warning)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def count(self) -> int:
        return self._count.value()


class MainWindow(QMainWindow):
    """Top-level editor window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Area Editor")
        self.setMinimumSize(640, 480)
        self._size_to_screen()
        self.setDockNestingEnabled(True)
        # Ensure standard window frame with resize handles
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        # State
        self._manifest: ProjectManifest | None = None
        self._catalog: TilesetCatalog | None = None
        self._templates: TemplateCatalog | None = None
        # Per-tab area documents keyed by content_id
        self._area_docs: dict[str, AreaDocument] = {}
        self._connected_canvas: TileCanvas | None = None
        self._active_brush_type: BrushType = BrushType.ERASER
        self._entity_brush_template_id: str | None = None
        self._entity_brush_supported: bool = False
        self._render_target_kind: str | None = None
        self._render_target_ref: int | str | None = None
        self._active_instance_entity_id: str | None = None
        self._json_dirty_bound: set[str] = set()
        self._display_width: int = 320
        self._display_height: int = 240

        # Central tabbed document area
        self._tab_widget = DocumentTabWidget()
        self.setCentralWidget(self._tab_widget)

        # Dock panels — left side: project content browser tabs
        self._area_panel = AreaListPanel()
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._area_panel)

        self._template_panel = TemplateListPanel()
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._template_panel)

        self._item_panel = FileTreePanel(
            "Items",
            object_name="ItemPanel",
            content_prefix="items",
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._item_panel)

        self._global_entities_panel = GlobalEntitiesPanel()
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._global_entities_panel)

        self._dialogue_panel = FileTreePanel(
            "Dialogues", object_name="DialoguePanel"
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._dialogue_panel)

        self._command_panel = FileTreePanel(
            "Commands", object_name="CommandPanel"
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._command_panel)

        self._asset_panel = FileTreePanel(
            "Assets",
            object_name="AssetPanel",
            file_extensions=(),  # show all file types
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._asset_panel)

        # Right side: layer panel + tileset browser
        self._layer_panel = LayerListPanel()
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._layer_panel)

        self._render_panel = RenderPropertiesPanel()
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._render_panel)

        self._entity_instance_panel = EntityInstanceJsonPanel()
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._entity_instance_panel)

        self._tileset_panel = TilesetBrowserPanel()
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._tileset_panel)

        # Build the left side as one browser stack on top plus a separate
        # entity-instance dock below it.
        self.splitDockWidget(self._area_panel, self._entity_instance_panel, Qt.Orientation.Vertical)
        self.tabifyDockWidget(self._area_panel, self._template_panel)
        self.tabifyDockWidget(self._template_panel, self._item_panel)
        self.tabifyDockWidget(self._item_panel, self._global_entities_panel)
        self.tabifyDockWidget(self._global_entities_panel, self._dialogue_panel)
        self.tabifyDockWidget(self._dialogue_panel, self._command_panel)
        self.tabifyDockWidget(self._command_panel, self._asset_panel)
        self.resizeDocks(
            [self._area_panel, self._entity_instance_panel],
            [430, 240],
            Qt.Orientation.Vertical,
        )
        self.resizeDocks(
            [self._area_panel, self._layer_panel],
            [560, 320],
            Qt.Orientation.Horizontal,
        )
        self._area_panel.raise_()  # show area list tab by default

        # Settings
        self._settings = QSettings("PuzzleDungeon", "AreaEditor")
        self._json_editing_enabled = bool(
            self._settings.value(_SETTINGS_KEY_JSON_EDITING_ENABLED, False, type=bool)
        )

        # Status bar
        self._status_area = QLabel("No project loaded")
        self._status_cell = QLabel("")
        self._status_layer = QLabel("")
        self._status_gid = QLabel("")
        self._status_zoom = QLabel("100%")
        self.statusBar().addWidget(self._status_area, 1)
        self.statusBar().addPermanentWidget(self._status_cell)
        self.statusBar().addPermanentWidget(self._status_layer)
        self.statusBar().addPermanentWidget(self._status_gid)
        self.statusBar().addPermanentWidget(self._status_zoom)

        # Menus
        self._build_menus()

        # Signals — side panel open requests (double-click / context menu)
        self._area_panel.area_open_requested.connect(self._on_area_open_requested)
        self._template_panel.file_open_requested.connect(
            lambda cid, fp: self._open_content(cid, fp, ContentType.ENTITY_TEMPLATE)
        )
        self._item_panel.file_open_requested.connect(
            lambda cid, fp: self._open_content(cid, fp, ContentType.ITEM)
        )
        self._global_entities_panel.global_entity_open_requested.connect(
            self._open_global_entities_tab
        )
        self._dialogue_panel.file_open_requested.connect(
            lambda cid, fp: self._open_content(cid, fp, ContentType.DIALOGUE)
        )
        self._command_panel.file_open_requested.connect(
            lambda cid, fp: self._open_content(cid, fp, ContentType.NAMED_COMMAND)
        )
        self._asset_panel.file_open_requested.connect(
            lambda cid, fp: self._open_content(cid, fp, ContentType.ASSET)
        )
        self._asset_panel.set_context_menu_builder(self._populate_asset_context_menu)

        # Tab widget signals
        self._tab_widget.active_tab_changed.connect(self._on_active_tab_changed)
        self._tab_widget.tab_close_requested.connect(self._on_tab_close_requested)
        self._tab_widget.tab_closed.connect(self._on_tab_closed)

        # Tileset browser + layer panel signals
        self._tileset_panel.tile_selected.connect(self._on_tile_selected)
        self._tileset_panel.add_tileset_requested.connect(self._on_add_tileset_requested)
        self._tileset_panel.edit_tileset_requested.connect(self._on_edit_tileset_requested)
        self._template_panel.template_brush_selected.connect(
            self._on_template_brush_selected
        )
        self._layer_panel.active_layer_changed.connect(self._on_active_layer_changed)
        self._render_panel.properties_changed.connect(self._on_render_properties_changed)
        self._entity_instance_panel.apply_requested.connect(self._on_apply_entity_instance_json)
        self._entity_instance_panel.revert_requested.connect(self._on_revert_entity_instance_json)
        self._entity_instance_panel.dirty_changed.connect(self._on_entity_instance_json_dirty_changed)
        self._entity_instance_panel.fields_apply_requested.connect(
            self._on_apply_entity_instance_fields
        )
        self._entity_instance_panel.fields_revert_requested.connect(
            self._on_revert_entity_instance_fields
        )
        self._entity_instance_panel.fields_dirty_changed.connect(
            self._on_entity_instance_fields_dirty_changed
        )

    # ------------------------------------------------------------------
    # Public API (called from __main__ for --project arg)
    # ------------------------------------------------------------------

    def open_project(self, project_path: Path) -> None:
        """Load a project manifest and populate the side panels."""
        if not self._maybe_save_dirty_tabs():
            return

        try:
            self._manifest = load_manifest(project_path)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to load project:\n{exc}")
            return

        # Remember this project for next time
        self._settings.setValue(
            _SETTINGS_KEY_LAST_PROJECT,
            str(project_path.resolve()),
        )

        resolver = AssetResolver(self._manifest.asset_paths)
        self._catalog = TilesetCatalog(resolver)
        self._templates = TemplateCatalog()
        self._templates.load_from_manifest(self._manifest)
        self._entity_instance_panel.set_template_catalog(self._templates)
        self._display_width = self._manifest.display_width
        self._display_height = self._manifest.display_height

        # Close all existing tabs
        self._tab_widget.close_all()
        self._area_docs.clear()
        self._connected_canvas = None
        self._active_brush_type = BrushType.ERASER
        self._entity_brush_template_id = None
        self._entity_brush_supported = False
        self._render_target_kind = None
        self._render_target_ref = None
        self._active_instance_entity_id = None
        self._json_dirty_bound.clear()
        self._layer_panel.clear_layers()
        self._render_panel.clear_target()
        self._entity_instance_panel.clear_entity()
        self._template_panel.set_brush_active(None)
        self._tileset_panel.clear_tilesets()
        self._sync_json_edit_actions()

        areas = discover_areas(self._manifest)
        self._area_panel.set_areas(areas)
        self._template_panel.set_templates(
            self._manifest, self._templates, self._catalog
        )
        self._item_panel.populate(self._manifest.item_paths)
        self._global_entities_panel.populate(discover_global_entities(self._manifest))
        self._dialogue_panel.populate(self._manifest.dialogue_paths)
        self._command_panel.populate(self._manifest.command_paths)
        self._asset_panel.populate(self._manifest.asset_paths)
        self._update_project_content_actions()

        project_name = self._manifest.project_root.name
        self.setWindowTitle(f"Area Editor - {project_name}")
        self._status_area.setText(f"Project: {project_name}")

        # Auto-open startup area if it exists
        if self._manifest.startup_area:
            for entry in areas:
                if entry.area_id == self._manifest.startup_area:
                    self._open_area(entry.area_id, entry.file_path)
                    self._area_panel.highlight_area(entry.area_id)
                    break

    # ------------------------------------------------------------------
    # Menu construction
    # ------------------------------------------------------------------

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        open_action = QAction("&Open Project...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._on_open_project)
        file_menu.addAction(open_action)

        self._new_area_action = QAction("&New Area...", self)
        self._new_area_action.setEnabled(False)
        self._new_area_action.triggered.connect(self._on_new_area)
        file_menu.addAction(self._new_area_action)

        file_menu.addSeparator()

        self._save_action = QAction("&Save", self)
        self._save_action.setShortcut(QKeySequence.StandardKey.Save)
        self._save_action.setEnabled(False)
        self._save_action.triggered.connect(self._on_save_active)
        file_menu.addAction(self._save_action)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        project_menu = self.menuBar().addMenu("&Project")

        self._open_project_manifest_action = QAction("Open Project Manifest", self)
        self._open_project_manifest_action.setEnabled(False)
        self._open_project_manifest_action.triggered.connect(self._open_project_manifest_tab)
        project_menu.addAction(self._open_project_manifest_action)

        self._open_shared_variables_action = QAction("Open Shared Variables", self)
        self._open_shared_variables_action.setEnabled(False)
        self._open_shared_variables_action.triggered.connect(self._open_shared_variables_tab)
        project_menu.addAction(self._open_shared_variables_action)

        self._open_global_entities_action = QAction("Open Global Entities", self)
        self._open_global_entities_action.setEnabled(False)
        self._open_global_entities_action.triggered.connect(
            lambda: self._open_global_entities_tab(None)
        )
        project_menu.addAction(self._open_global_entities_action)

        edit_menu = self.menuBar().addMenu("&Edit")

        self._paint_tiles_action = QAction("&Paint", self)
        self._paint_tiles_action.setCheckable(True)
        self._paint_tiles_action.setEnabled(False)
        self._paint_tiles_action.setShortcut(QKeySequence("P"))
        self._paint_tiles_action.toggled.connect(self._on_paint_tiles_toggled)
        edit_menu.addAction(self._paint_tiles_action)

        self._select_action = QAction("&Select", self)
        self._select_action.setCheckable(True)
        self._select_action.setEnabled(False)
        self._select_action.setShortcut(QKeySequence("S"))
        self._select_action.toggled.connect(self._on_select_toggled)
        edit_menu.addAction(self._select_action)

        self._enable_json_editing_action = QAction("Enable JSON Editing", self)
        self._enable_json_editing_action.setCheckable(True)
        self._enable_json_editing_action.setChecked(self._json_editing_enabled)
        self._enable_json_editing_action.toggled.connect(self._on_toggle_json_editing)
        edit_menu.addAction(self._enable_json_editing_action)

        self._cell_flags_action = QAction("Edit Cell &Flags", self)
        self._cell_flags_action.setCheckable(True)
        self._cell_flags_action.setEnabled(False)
        self._cell_flags_action.toggled.connect(self._on_cell_flags_toggled)
        edit_menu.addAction(self._cell_flags_action)

        self._delete_selected_entity_action = QAction(self)
        self._delete_selected_entity_action.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        self._delete_selected_entity_action.triggered.connect(
            self._on_delete_selected_entity
        )
        self.addAction(self._delete_selected_entity_action)

        self._clear_selection_action = QAction(self)
        self._clear_selection_action.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        self._clear_selection_action.triggered.connect(self._on_clear_selection)
        self.addAction(self._clear_selection_action)

        self._nudge_left_action = QAction(self)
        self._nudge_left_action.setShortcut(QKeySequence(Qt.Key.Key_Left))
        self._nudge_left_action.triggered.connect(lambda: self._on_nudge_selected_entity(-1, 0))
        self.addAction(self._nudge_left_action)

        self._nudge_right_action = QAction(self)
        self._nudge_right_action.setShortcut(QKeySequence(Qt.Key.Key_Right))
        self._nudge_right_action.triggered.connect(lambda: self._on_nudge_selected_entity(1, 0))
        self.addAction(self._nudge_right_action)

        self._nudge_up_action = QAction(self)
        self._nudge_up_action.setShortcut(QKeySequence(Qt.Key.Key_Up))
        self._nudge_up_action.triggered.connect(lambda: self._on_nudge_selected_entity(0, -1))
        self.addAction(self._nudge_up_action)

        self._nudge_down_action = QAction(self)
        self._nudge_down_action.setShortcut(QKeySequence(Qt.Key.Key_Down))
        self._nudge_down_action.triggered.connect(lambda: self._on_nudge_selected_entity(0, 1))
        self.addAction(self._nudge_down_action)

        self._nudge_left_pixels_action = QAction(self)
        self._nudge_left_pixels_action.setShortcut(QKeySequence("Shift+Left"))
        self._nudge_left_pixels_action.triggered.connect(lambda: self._on_nudge_screen_entity(-8, 0))
        self.addAction(self._nudge_left_pixels_action)

        self._nudge_right_pixels_action = QAction(self)
        self._nudge_right_pixels_action.setShortcut(QKeySequence("Shift+Right"))
        self._nudge_right_pixels_action.triggered.connect(lambda: self._on_nudge_screen_entity(8, 0))
        self.addAction(self._nudge_right_pixels_action)

        self._nudge_up_pixels_action = QAction(self)
        self._nudge_up_pixels_action.setShortcut(QKeySequence("Shift+Up"))
        self._nudge_up_pixels_action.triggered.connect(lambda: self._on_nudge_screen_entity(0, -8))
        self.addAction(self._nudge_up_pixels_action)

        self._nudge_down_pixels_action = QAction(self)
        self._nudge_down_pixels_action.setShortcut(QKeySequence("Shift+Down"))
        self._nudge_down_pixels_action.triggered.connect(lambda: self._on_nudge_screen_entity(0, 8))
        self.addAction(self._nudge_down_pixels_action)

        # View menu
        view_menu = self.menuBar().addMenu("&View")

        self._grid_action = QAction("Show &Grid", self)
        self._grid_action.setCheckable(True)
        self._grid_action.setChecked(True)
        self._grid_action.toggled.connect(self._on_grid_toggled)
        view_menu.addAction(self._grid_action)

        reset_zoom_action = QAction("Reset &Zoom", self)
        reset_zoom_action.setShortcut(QKeySequence("Ctrl+0"))
        reset_zoom_action.triggered.connect(self._on_reset_zoom)
        view_menu.addAction(reset_zoom_action)

        area_menu = self.menuBar().addMenu("&Area")

        self._add_rows_above_action = QAction("Add Rows Above...", self)
        self._add_rows_above_action.setEnabled(False)
        self._add_rows_above_action.triggered.connect(
            lambda: self._on_change_area_extent("add_rows_above")
        )
        area_menu.addAction(self._add_rows_above_action)

        self._add_rows_below_action = QAction("Add Rows Below...", self)
        self._add_rows_below_action.setEnabled(False)
        self._add_rows_below_action.triggered.connect(
            lambda: self._on_change_area_extent("add_rows_below")
        )
        area_menu.addAction(self._add_rows_below_action)

        self._add_columns_left_action = QAction("Add Columns Left...", self)
        self._add_columns_left_action.setEnabled(False)
        self._add_columns_left_action.triggered.connect(
            lambda: self._on_change_area_extent("add_columns_left")
        )
        area_menu.addAction(self._add_columns_left_action)

        self._add_columns_right_action = QAction("Add Columns Right...", self)
        self._add_columns_right_action.setEnabled(False)
        self._add_columns_right_action.triggered.connect(
            lambda: self._on_change_area_extent("add_columns_right")
        )
        area_menu.addAction(self._add_columns_right_action)

        area_menu.addSeparator()

        self._remove_top_rows_action = QAction("Remove Top Rows...", self)
        self._remove_top_rows_action.setEnabled(False)
        self._remove_top_rows_action.triggered.connect(
            lambda: self._on_change_area_extent("remove_top_rows")
        )
        area_menu.addAction(self._remove_top_rows_action)

        self._remove_bottom_rows_action = QAction("Remove Bottom Rows...", self)
        self._remove_bottom_rows_action.setEnabled(False)
        self._remove_bottom_rows_action.triggered.connect(
            lambda: self._on_change_area_extent("remove_bottom_rows")
        )
        area_menu.addAction(self._remove_bottom_rows_action)

        self._remove_left_columns_action = QAction("Remove Left Columns...", self)
        self._remove_left_columns_action.setEnabled(False)
        self._remove_left_columns_action.triggered.connect(
            lambda: self._on_change_area_extent("remove_left_columns")
        )
        area_menu.addAction(self._remove_left_columns_action)

        self._remove_right_columns_action = QAction("Remove Right Columns...", self)
        self._remove_right_columns_action.setEnabled(False)
        self._remove_right_columns_action.triggered.connect(
            lambda: self._on_change_area_extent("remove_right_columns")
        )
        area_menu.addAction(self._remove_right_columns_action)

    # ------------------------------------------------------------------
    # Slots — file dialog
    # ------------------------------------------------------------------

    def _on_open_project(self) -> None:
        # Pre-navigate to last opened project's location
        start_dir = ""
        last = self._settings.value(_SETTINGS_KEY_LAST_PROJECT, "")
        if last:
            last_path = Path(str(last))
            if last_path.is_file():
                start_dir = str(last_path.parent)
            elif last_path.is_dir():
                start_dir = str(last_path)
            elif last_path.parent.is_dir():
                start_dir = str(last_path.parent)

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            start_dir,
            "Project manifest (project.json);;All files (*)",
        )
        if path:
            self.open_project(Path(path))

    def _on_new_area(self) -> None:
        if self._manifest is None:
            return
        dialog = _NewAreaDialog(self, tile_size=16)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            area_id, file_path = self._create_new_area_file(
                area_id=dialog.area_id,
                display_name=dialog.display_name,
                width=dialog.width,
                height=dialog.height,
                tile_size=dialog.tile_size,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "New Area", str(exc))
            return
        self._refresh_area_panel()
        self._open_area(area_id, file_path)
        self._area_panel.highlight_area(area_id)
        self.statusBar().showMessage(f"Created area {area_id}.", 2500)

    def _create_new_area_file(
        self,
        *,
        area_id: str,
        display_name: str,
        width: int,
        height: int,
        tile_size: int,
    ) -> tuple[str, Path]:
        if self._manifest is None:
            raise ValueError("Open a project before creating an area.")
        normalized_id = area_id.strip().replace("\\", "/").strip("/")
        if not normalized_id:
            raise ValueError("Area ID must not be empty.")
        if normalized_id.endswith(".json"):
            normalized_id = normalized_id[:-5]
        area_root = self._default_area_root()
        file_path = (area_root / Path(normalized_id)).with_suffix(".json")
        content_id = f"{AREA_ID_PREFIX}/{normalized_id}"
        if file_path.exists():
            raise ValueError(f"An area already exists at {content_id}.")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if area_root not in self._manifest.area_paths:
            self._manifest.area_paths.append(area_root)
        document = make_empty_area_document(
            name=display_name or normalized_id.rsplit("/", 1)[-1],
            width=width,
            height=height,
            tile_size=tile_size,
            include_default_ground_layer=True,
        )
        save_area_document(file_path, document)
        return content_id, file_path

    def _default_area_root(self) -> Path:
        if self._manifest is None:
            raise ValueError("No project is open.")
        if self._manifest.area_paths:
            return self._manifest.area_paths[0]
        return (self._manifest.project_root / AREA_ID_PREFIX).resolve()

    def _refresh_area_panel(self) -> None:
        if self._manifest is None:
            return
        self._area_panel.set_areas(discover_areas(self._manifest))

    def _on_change_area_extent(self, operation: str) -> None:
        context = self._active_area_context()
        if context is None:
            return
        content_id, doc, canvas = context
        config = self._area_extent_operation_config(operation)
        dialog = _AreaCountDialog(
            self,
            title=config["title"],
            label=config["label"],
            warning_text=config["warning"],
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        count = dialog.count
        screen_entity_ids = self._screen_space_entity_ids(doc)
        succeeded, blocked = self._apply_area_extent_operation(
            doc,
            operation,
            count,
            screen_entity_ids=screen_entity_ids,
        )
        if blocked:
            QMessageBox.warning(
                self,
                "Area Resize Blocked",
                blocked,
            )
            return
        if not succeeded:
            return
        canvas.refresh_scene_contents()
        if canvas.selected_entity_id:
            canvas.set_selected_entity(
                canvas.selected_entity_id,
                cycle_position=1,
                cycle_total=1,
                emit=False,
            )
        self._tab_widget.set_dirty(content_id, True)
        self._refresh_render_properties_target()
        self._refresh_entity_instance_panel()
        self._update_paint_status()
        self.statusBar().showMessage(config["status"].format(count=count), 2500)

    def _area_extent_operation_config(self, operation: str) -> dict[str, str]:
        return {
            "add_rows_above": {
                "title": "Add Rows Above",
                "label": "Rows to add",
                "warning": "Empty rows will be inserted above the current area.",
                "status": "Added {count} row(s) above.",
            },
            "add_rows_below": {
                "title": "Add Rows Below",
                "label": "Rows to add",
                "warning": "Empty rows will be inserted below the current area.",
                "status": "Added {count} row(s) below.",
            },
            "add_columns_left": {
                "title": "Add Columns Left",
                "label": "Columns to add",
                "warning": "Empty columns will be inserted on the left side.",
                "status": "Added {count} column(s) left.",
            },
            "add_columns_right": {
                "title": "Add Columns Right",
                "label": "Columns to add",
                "warning": "Empty columns will be inserted on the right side.",
                "status": "Added {count} column(s) right.",
            },
            "remove_top_rows": {
                "title": "Remove Top Rows",
                "label": "Rows to remove",
                "warning": "Tiles on the top edge will be discarded.",
                "status": "Removed {count} top row(s).",
            },
            "remove_bottom_rows": {
                "title": "Remove Bottom Rows",
                "label": "Rows to remove",
                "warning": "Tiles on the bottom edge will be discarded.",
                "status": "Removed {count} bottom row(s).",
            },
            "remove_left_columns": {
                "title": "Remove Left Columns",
                "label": "Columns to remove",
                "warning": "Tiles on the left edge will be discarded.",
                "status": "Removed {count} left column(s).",
            },
            "remove_right_columns": {
                "title": "Remove Right Columns",
                "label": "Columns to remove",
                "warning": "Tiles on the right edge will be discarded.",
                "status": "Removed {count} right column(s).",
            },
        }[operation]

    def _apply_area_extent_operation(
        self,
        doc: AreaDocument,
        operation: str,
        count: int,
        *,
        screen_entity_ids: set[str],
    ) -> tuple[bool, str | None]:
        if operation == "add_rows_above":
            return add_rows_above(doc, count, screen_entity_ids=screen_entity_ids), None
        if operation == "add_rows_below":
            return add_rows_below(doc, count), None
        if operation == "add_columns_left":
            return add_columns_left(doc, count, screen_entity_ids=screen_entity_ids), None
        if operation == "add_columns_right":
            return add_columns_right(doc, count), None
        if operation == "remove_top_rows":
            if not can_remove_top_rows(doc, count, screen_entity_ids=screen_entity_ids):
                return False, "Cannot remove top rows because one or more world-space entities would fall outside the area bounds."
            return remove_top_rows(doc, count, screen_entity_ids=screen_entity_ids), None
        if operation == "remove_bottom_rows":
            if not can_remove_bottom_rows(doc, count, screen_entity_ids=screen_entity_ids):
                return False, "Cannot remove bottom rows because one or more world-space entities would fall outside the area bounds."
            return remove_bottom_rows(doc, count, screen_entity_ids=screen_entity_ids), None
        if operation == "remove_left_columns":
            if not can_remove_left_columns(doc, count, screen_entity_ids=screen_entity_ids):
                return False, "Cannot remove left columns because one or more world-space entities would fall outside the area bounds."
            return remove_left_columns(doc, count, screen_entity_ids=screen_entity_ids), None
        if operation == "remove_right_columns":
            if not can_remove_right_columns(doc, count, screen_entity_ids=screen_entity_ids):
                return False, "Cannot remove right columns because one or more world-space entities would fall outside the area bounds."
            return remove_right_columns(doc, count, screen_entity_ids=screen_entity_ids), None
        return False, None

    # ------------------------------------------------------------------
    # Slots — side panel open requests
    # ------------------------------------------------------------------

    def _on_area_open_requested(self, area_id: str, file_path: Path) -> None:
        self._open_area(area_id, file_path)

    def _open_content(
        self, content_id: str, file_path: Path, content_type: ContentType
    ) -> None:
        """Open a non-area content item in a tab."""
        self._open_content_widget(content_id, file_path, content_type, None)

    def _open_content_widget(
        self,
        content_id: str,
        file_path: Path,
        content_type: ContentType,
        widget: QWidget | None,
    ) -> QWidget:
        if widget is None and content_type == ContentType.ENTITY_TEMPLATE:
            widget = EntityTemplateEditorWidget(content_id, file_path)
        if widget is None and content_type == ContentType.ITEM:
            widget = ItemEditorWidget(content_id, file_path)
        opened_widget = self._tab_widget.open_tab(
            content_id,
            file_path,
            content_type,
            widget=widget,
        )
        if (
            isinstance(
                opened_widget,
                (
                    JsonViewerWidget,
                    GlobalEntitiesEditorWidget,
                    EntityTemplateEditorWidget,
                    ItemEditorWidget,
                ),
            )
            and content_id not in self._json_dirty_bound
        ):
            opened_widget.dirty_changed.connect(
                lambda dirty, cid=content_id: self._tab_widget.set_dirty(cid, dirty)
            )
            self._json_dirty_bound.add(content_id)
        self._sync_json_edit_actions()
        return opened_widget

    def _open_project_manifest_tab(self) -> None:
        if self._manifest is None:
            return
        self._open_content(
            "project/project",
            self._manifest.project_file,
            ContentType.PROJECT_MANIFEST,
        )

    def _open_shared_variables_tab(self) -> None:
        if self._manifest is None or self._manifest.shared_variables_path is None:
            return
        self._open_content(
            "project/shared_variables",
            self._manifest.shared_variables_path,
            ContentType.SHARED_VARIABLES,
        )

    def _open_global_entities_tab(self, entity_id: str | None) -> None:
        if self._manifest is None:
            return
        content_id = "project/global_entities"
        widget = self._tab_widget.widget_for_content(content_id)
        if not isinstance(widget, GlobalEntitiesEditorWidget):
            widget = GlobalEntitiesEditorWidget(self._manifest.project_file)
            self._open_content_widget(
                content_id,
                self._manifest.project_file,
                ContentType.GLOBAL_ENTITIES,
                widget,
            )
        else:
            self._tab_widget.open_tab(
                content_id,
                self._manifest.project_file,
                ContentType.GLOBAL_ENTITIES,
            )
        widget.select_entity_id(entity_id)
        if entity_id:
            self._global_entities_panel.select_entity(entity_id)

    # ------------------------------------------------------------------
    # Slots — tab widget
    # ------------------------------------------------------------------

    def _on_active_tab_changed(self, content_id: str, content_type: object) -> None:
        """Update layer panel, tileset browser, and status bar when the active tab changes."""
        if content_type == ContentType.AREA and content_id in self._area_docs:
            doc = self._area_docs[content_id]
            self._layer_panel.set_layers(doc.tile_layers)
            self._status_area.setText(doc.name or content_id)
            self._save_action.setEnabled(True)
            self._cell_flags_action.setEnabled(True)
            self._set_area_actions_enabled(True)

            # Populate tileset browser for this area
            if self._catalog is not None:
                canvas = self._active_canvas()
                current_index = canvas.tileset_index_hint if canvas is not None else 0
                selected_gid = canvas.selected_gid if canvas is not None else 0
                erase_mode = canvas.brush_erase_mode if canvas is not None else True
                self._tileset_panel.set_tilesets(
                    doc.tilesets,
                    self._catalog,
                    current_index=current_index,
                    selected_gid=selected_gid,
                    erase_mode=erase_mode,
                )

            # Reconnect layer visibility signals to the active canvas
            canvas = self._active_canvas()
            if canvas is not None:
                self._layer_panel.set_active_layer(canvas.active_layer)
                self._connect_canvas(canvas)
                can_paint = bool(doc.tile_layers)
                self._paint_tiles_action.setEnabled(can_paint)
                self._select_action.setEnabled(True)
                self._set_cell_flags_action_state(canvas.cell_flags_edit_mode)
                self._set_paint_tiles_action_state(canvas.tile_paint_mode)
                self._set_select_action_state(canvas.select_mode)
                self._apply_active_brush_to_canvas(canvas)
                self._status_zoom.setText(f"{canvas.zoom_level:.0%}")
                self._refresh_render_properties_target()
                self._refresh_entity_instance_panel()
                self._sync_json_edit_actions()
                if can_paint or canvas.select_mode:
                    self._update_paint_status()
                else:
                    self._status_layer.setText("")
                    self._status_gid.setText("")
        elif content_id:
            self._layer_panel.clear_layers()
            self._tileset_panel.clear_tilesets()
            self._status_area.setText(self._status_label_for_content(content_id, content_type))
            self._status_cell.setText("")
            self._status_layer.setText("")
            self._status_gid.setText("")
            self._status_zoom.setText("")
            self._save_action.setEnabled(self._active_json_widget() is not None)
            self._cell_flags_action.setEnabled(False)
            self._paint_tiles_action.setEnabled(False)
            self._select_action.setEnabled(False)
            self._set_area_actions_enabled(False)
            self._set_cell_flags_action_state(False)
            self._set_paint_tiles_action_state(False)
            self._set_select_action_state(False)
            self._render_target_kind = None
            self._render_target_ref = None
            self._render_panel.clear_target()
            self._active_instance_entity_id = None
            self._entity_instance_panel.clear_entity()
            self._sync_json_edit_actions()
        else:
            # No tabs open
            self._layer_panel.clear_layers()
            self._tileset_panel.clear_tilesets()
            project_name = (
                self._manifest.project_root.name if self._manifest else ""
            )
            self._status_area.setText(
                f"Project: {project_name}" if project_name else "No project loaded"
            )
            self._status_cell.setText("")
            self._status_layer.setText("")
            self._status_gid.setText("")
            self._status_zoom.setText("")
            self._save_action.setEnabled(False)
            self._cell_flags_action.setEnabled(False)
            self._paint_tiles_action.setEnabled(False)
            self._select_action.setEnabled(False)
            self._set_area_actions_enabled(False)
            self._set_cell_flags_action_state(False)
            self._set_paint_tiles_action_state(False)
            self._set_select_action_state(False)
            self._render_target_kind = None
            self._render_target_ref = None
            self._render_panel.clear_target()
            self._active_instance_entity_id = None
            self._entity_instance_panel.clear_entity()
            self._sync_json_edit_actions()

    def _status_label_for_content(self, content_id: str, content_type: object) -> str:
        if content_type == ContentType.PROJECT_MANIFEST:
            return "Project Manifest"
        if content_type == ContentType.SHARED_VARIABLES:
            return "Shared Variables"
        if content_type == ContentType.GLOBAL_ENTITIES:
            return "Global Entities"
        return content_id

    def _update_project_content_actions(self) -> None:
        has_manifest = self._manifest is not None and self._manifest.project_file.is_file()
        has_shared_variables = (
            self._manifest is not None
            and self._manifest.shared_variables_path is not None
            and self._manifest.shared_variables_path.is_file()
        )
        self._new_area_action.setEnabled(self._manifest is not None)
        self._open_project_manifest_action.setEnabled(has_manifest)
        self._open_shared_variables_action.setEnabled(has_shared_variables)
        self._open_global_entities_action.setEnabled(has_manifest)

    def _set_area_actions_enabled(self, enabled: bool) -> None:
        for action in (
            self._add_rows_above_action,
            self._add_rows_below_action,
            self._add_columns_left_action,
            self._add_columns_right_action,
            self._remove_top_rows_action,
            self._remove_bottom_rows_action,
            self._remove_left_columns_action,
            self._remove_right_columns_action,
        ):
            action.setEnabled(enabled)

    def _refresh_project_metadata_surfaces(self) -> None:
        """Reload manifest-backed non-area editor surfaces after project-level saves."""
        if self._manifest is None:
            return
        try:
            refreshed = load_manifest(self._manifest.project_file)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Project Metadata Stale",
                f"Saved, but project metadata could not be reloaded:\n{exc}",
            )
            return
        self._manifest = refreshed
        resolver = AssetResolver(self._manifest.asset_paths)
        self._catalog = TilesetCatalog(resolver)
        self._templates = TemplateCatalog()
        self._templates.load_from_manifest(self._manifest)
        self._entity_instance_panel.set_template_catalog(self._templates)
        self._display_width = self._manifest.display_width
        self._display_height = self._manifest.display_height
        self._template_panel.set_templates(
            self._manifest, self._templates, self._catalog
        )
        self._item_panel.populate(self._manifest.item_paths)
        self._global_entities_panel.populate(discover_global_entities(self._manifest))
        self._dialogue_panel.populate(self._manifest.dialogue_paths)
        self._command_panel.populate(self._manifest.command_paths)
        self._asset_panel.populate(self._manifest.asset_paths)
        self._update_project_content_actions()

    def _refresh_template_surfaces(self) -> None:
        """Reload template-derived editor surfaces after template saves."""
        if self._manifest is None:
            return
        self._templates = TemplateCatalog()
        self._templates.load_from_manifest(self._manifest)
        self._entity_instance_panel.set_template_catalog(self._templates)
        if self._catalog is not None:
            self._template_panel.set_templates(
                self._manifest,
                self._templates,
                self._catalog,
            )

    def _on_tab_close_requested(self, content_id: str, _content_type: object) -> None:
        if not self._maybe_save_dirty_tabs([content_id]):
            return
        self._tab_widget.close_content(content_id)

    def _on_tab_closed(self, content_id: str) -> None:
        self._area_docs.pop(content_id, None)
        self._json_dirty_bound.discard(content_id)

    # ------------------------------------------------------------------
    # Slots — view menu
    # ------------------------------------------------------------------

    def _on_grid_toggled(self, visible: bool) -> None:
        canvas = self._active_canvas()
        if canvas is not None:
            canvas.set_grid_visible(visible)

    def _on_reset_zoom(self) -> None:
        canvas = self._active_canvas()
        if canvas is not None:
            canvas.reset_zoom()

    def _on_paint_tiles_toggled(self, enabled: bool) -> None:
        canvas = self._active_canvas()
        if canvas is None:
            self._set_paint_tiles_action_state(False)
            return
        # Mutually exclusive with select + cell-flag mode
        if enabled and self._select_action.isChecked():
            self._set_select_action_state(False)
            canvas.set_select_mode(False)
        if enabled and self._cell_flags_action.isChecked():
            self._set_cell_flags_action_state(False)
            canvas.set_cell_flags_edit_mode(False)
        canvas.set_tile_paint_mode(enabled)
        if enabled:
            self._tileset_panel.show()
            self._tileset_panel.raise_()
            self._update_paint_status()
            self.statusBar().showMessage(
                "Paint mode: left-click uses the active brush, right-click erases tiles or deletes entities, Alt+click eyedrops tiles.",
                4000,
            )
        else:
            self._update_paint_status()

    def _on_select_toggled(self, enabled: bool) -> None:
        canvas = self._active_canvas()
        if canvas is None:
            self._set_select_action_state(False)
            return
        if enabled and self._paint_tiles_action.isChecked():
            self._set_paint_tiles_action_state(False)
            canvas.set_tile_paint_mode(False)
        if enabled and self._cell_flags_action.isChecked():
            self._set_cell_flags_action_state(False)
            canvas.set_cell_flags_edit_mode(False)
        canvas.set_select_mode(enabled)
        if enabled:
            self._update_paint_status()
            self.statusBar().showMessage(
                "Select mode: click entities to select, click again to cycle, Delete removes, arrows nudge, Escape clears.",
                4000,
            )
        else:
            self._update_paint_status()

    def _on_toggle_json_editing(self, enabled: bool) -> None:
        self._json_editing_enabled = enabled
        self._settings.setValue(_SETTINGS_KEY_JSON_EDITING_ENABLED, enabled)
        self._apply_json_editing_state()
        message = "JSON editing enabled." if enabled else "JSON editing locked."
        self.statusBar().showMessage(message, 2000)

    def _on_cell_flags_toggled(self, enabled: bool) -> None:
        canvas = self._active_canvas()
        if canvas is None:
            self._set_cell_flags_action_state(False)
            return
        # Mutually exclusive with paint/select modes
        if enabled and self._select_action.isChecked():
            self._set_select_action_state(False)
            canvas.set_select_mode(False)
        if enabled and self._paint_tiles_action.isChecked():
            self._set_paint_tiles_action_state(False)
            canvas.set_tile_paint_mode(False)
            self._update_paint_status()
        canvas.set_cell_flags_edit_mode(enabled)
        if enabled:
            self.statusBar().showMessage(
                "Cell flag edit mode: left-click walkable, right-click blocked.",
                4000,
            )

    def _on_tile_selected(self, gid: int) -> None:
        canvas = self._active_canvas()
        if canvas is not None:
            canvas.set_selected_gid(gid)
            canvas.set_tileset_index_hint(self._tileset_panel.current_tileset_index)
            canvas.set_brush_erase_mode(self._tileset_panel.brush_is_erase)
            canvas.set_active_brush_type(
                BrushType.ERASER if self._tileset_panel.brush_is_erase else BrushType.TILE
            )
        self._active_brush_type = (
            BrushType.ERASER if self._tileset_panel.brush_is_erase else BrushType.TILE
        )
        self._tileset_panel.set_brush_active(True)
        self._template_panel.set_brush_active(None)
        self._ensure_paint_mode()
        self._update_paint_status()

    def _on_template_brush_selected(self, template_id: str) -> None:
        self._entity_brush_template_id = template_id
        self._active_brush_type = BrushType.ENTITY
        self._entity_brush_supported = True
        self._template_panel.set_brush_active(template_id)
        self._tileset_panel.set_brush_active(False)

        canvas = self._active_canvas()
        if canvas is not None:
            self._apply_entity_brush_to_canvas(canvas)
            canvas.set_active_brush_type(BrushType.ENTITY)

        self._ensure_paint_mode()
        self._update_paint_status()

    def _on_active_layer_changed(self, index: int) -> None:
        canvas = self._active_canvas()
        if canvas is not None:
            canvas.set_active_layer(index)
        self._set_render_target_layer(index)
        self._update_paint_status()

    def _on_add_tileset_requested(self) -> None:
        self._add_tileset_to_active_area()

    def _on_edit_tileset_requested(self, index: int) -> None:
        self._edit_tileset_in_active_area(index)

    def _on_render_properties_changed(
        self,
        render_order: int,
        y_sort: bool,
        sort_y_offset: float,
        stack_order: int,
    ) -> None:
        context = self._active_area_context()
        if context is None:
            return

        content_id, doc, canvas = context
        if self._render_target_kind == "entity":
            entity_id = self._render_target_ref if isinstance(self._render_target_ref, str) else None
            if not entity_id:
                return
            entity = entity_by_id(doc, entity_id)
            if entity is None:
                return
            if (
                entity.render_order == render_order
                and entity.y_sort == y_sort
                and entity.sort_y_offset == sort_y_offset
                and entity.stack_order == stack_order
            ):
                return
            entity.render_order = render_order
            entity.y_sort = y_sort
            entity.sort_y_offset = sort_y_offset
            entity.stack_order = stack_order
            canvas.refresh_scene_contents()
            self._tab_widget.set_dirty(content_id, True)
            self._refresh_render_properties_target()
            self.statusBar().showMessage(
                f"Updated render properties for entity {entity.id}.",
                2500,
            )
            return

        index = self._render_target_ref if isinstance(self._render_target_ref, int) else self._layer_panel.active_layer
        if not (0 <= index < len(doc.tile_layers)):
            return
        layer = doc.tile_layers[index]
        if (
            layer.render_order == render_order
            and layer.y_sort == y_sort
            and layer.sort_y_offset == sort_y_offset
            and layer.stack_order == stack_order
        ):
            return
        layer.render_order = render_order
        layer.y_sort = y_sort
        layer.sort_y_offset = sort_y_offset
        layer.stack_order = stack_order
        self._layer_panel.update_layer(index, layer)
        canvas.refresh_scene_contents()
        self._tab_widget.set_dirty(content_id, True)
        self._refresh_render_properties_target()
        self.statusBar().showMessage(
            f"Updated render properties for layer {layer.name}.",
            2500,
        )

    def _on_save_active(self) -> None:
        info = self._tab_widget.active_info()
        if info is None:
            return
        if self._save_content(info.content_id):
            self.statusBar().showMessage(f"Saved {info.content_id}", 3000)

    # ------------------------------------------------------------------
    # Slots — canvas status
    # ------------------------------------------------------------------

    def _on_cell_hovered(self, col: int, row: int) -> None:
        info = self._tab_widget.active_info()
        if info is None or info.content_type != ContentType.AREA:
            return
        doc = self._area_docs.get(info.content_id)
        if doc is None:
            return
        if 0 <= col < doc.width and 0 <= row < doc.height:
            self._status_cell.setText(f"Cell: ({col}, {row})")
        else:
            self._status_cell.setText("")
        self._update_paint_status()

    def _on_screen_pixel_hovered(self, px: int, py: int) -> None:
        if px < 0 or py < 0:
            self._status_cell.setText("")
            self._update_paint_status()
            return
        self._status_cell.setText(f"Pixel: ({px}, {py})")
        self._status_layer.setText("")

    def _on_zoom_changed(self, zoom: float) -> None:
        self._status_zoom.setText(f"{zoom:.0%}")

    def _on_cell_flag_edited(self, col: int, row: int, walkable: bool) -> None:
        info = self._tab_widget.active_info()
        if info is None or info.content_type != ContentType.AREA:
            return
        self._tab_widget.set_dirty(info.content_id, True)
        state = "walkable" if walkable else "blocked"
        self.statusBar().showMessage(
            f"Set cell ({col}, {row}) to {state}.",
            2500,
        )

    def _on_entity_selection_changed(
        self,
        entity_id: str,
        cycle_position: int,
        cycle_total: int,
    ) -> None:
        if not self._prepare_for_entity_instance_target_change(entity_id or None):
            canvas = self._active_canvas()
            if canvas is not None:
                if self._active_instance_entity_id:
                    canvas.set_selected_entity(self._active_instance_entity_id, emit=False)
                else:
                    canvas.clear_selected_entity(emit=False)
            return
        if entity_id:
            self._set_render_target_entity(entity_id)
            self._active_instance_entity_id = entity_id
        else:
            self._set_render_target_layer(self._layer_panel.active_layer)
            self._active_instance_entity_id = None
        self._refresh_entity_instance_panel()
        self._sync_json_edit_actions()
        self._update_paint_status()
        if not entity_id:
            self.statusBar().showMessage("Selection cleared.", 2000)
            return
        context = self._active_area_context()
        if context is None:
            return
        _content_id, doc, _canvas = context
        entity = entity_by_id(doc, entity_id)
        if entity is None:
            return
        template = entity.template.rsplit("/", 1)[-1] if entity.template else "entity"
        detail = f" ({cycle_position} of {cycle_total})" if cycle_total > 1 else ""
        self.statusBar().showMessage(
            f"Selected {entity.id} [{template}]{detail}.",
            2500,
        )

    def _on_entity_instance_json_dirty_changed(self, dirty: bool) -> None:
        if not dirty:
            return
        self.statusBar().showMessage("Selected entity JSON has unapplied changes.", 2000)

    def _on_entity_instance_fields_dirty_changed(self, dirty: bool) -> None:
        if not dirty:
            return
        self.statusBar().showMessage("Selected entity fields have unapplied changes.", 2000)

    def _on_entity_paint_requested(self, template_id: str, col: int, row: int) -> None:
        context = self._active_area_context()
        if context is None or not self._entity_brush_supported:
            return
        content_id, doc, canvas = context
        entity_id = self._generate_project_unique_entity_id(doc, template_id)
        created = place_entity(
            doc,
            template_id,
            col,
            row,
            entity_id=entity_id,
            render_order=self._entity_render_order(template_id),
            y_sort=True,
        )
        canvas.refresh_scene_contents()
        self._tab_widget.set_dirty(content_id, True)
        self.statusBar().showMessage(
            f"Placed {created.id} at ({col}, {row}).",
            2500,
        )

    def _on_entity_screen_paint_requested(
        self,
        template_id: str,
        pixel_x: int,
        pixel_y: int,
    ) -> None:
        context = self._active_area_context()
        if context is None or not self._entity_brush_supported:
            return
        content_id, doc, canvas = context
        entity_id = self._generate_project_unique_entity_id(doc, template_id)
        created = place_screen_entity(
            doc,
            template_id,
            pixel_x,
            pixel_y,
            entity_id=entity_id,
            render_order=self._entity_render_order(template_id),
            y_sort=False,
        )
        canvas.refresh_scene_contents()
        canvas.set_selected_entity(created.id, cycle_position=1, cycle_total=1, emit=False)
        self._active_instance_entity_id = created.id
        self._set_render_target_entity(created.id)
        self._refresh_entity_instance_panel()
        self._tab_widget.set_dirty(content_id, True)
        self._update_paint_status()
        self.statusBar().showMessage(
            f"Placed screen entity {created.id} at pixel ({pixel_x}, {pixel_y}).",
            2500,
        )

    def _on_entity_delete_requested(self, col: int, row: int) -> None:
        context = self._active_area_context()
        if context is None:
            return
        content_id, doc, canvas = context
        deleted_id = self._delete_world_entity_at(doc, col, row)
        if deleted_id is None:
            return
        if canvas.selected_entity_id == deleted_id:
            canvas.clear_selected_entity(emit=False)
            self._set_render_target_layer(self._layer_panel.active_layer)
        canvas.refresh_scene_contents()
        self._tab_widget.set_dirty(content_id, True)
        self._update_paint_status()
        self.statusBar().showMessage(
            f"Deleted {deleted_id} from ({col}, {row}).",
            2500,
        )

    def _on_delete_selected_entity(self) -> None:
        context = self._active_area_context()
        if context is None or not self._select_action.isChecked():
            return
        content_id, doc, canvas = context
        selected_id = canvas.selected_entity_id
        if not selected_id:
            return
        deleted_id = delete_entity_by_id(doc, selected_id)
        if deleted_id is None:
            return
        canvas.clear_selected_entity(emit=False)
        self._set_render_target_layer(self._layer_panel.active_layer)
        canvas.refresh_scene_contents()
        self._tab_widget.set_dirty(content_id, True)
        self._update_paint_status()
        self.statusBar().showMessage(f"Deleted {deleted_id}.", 2500)

    def _on_clear_selection(self) -> None:
        canvas = self._active_canvas()
        if canvas is None or not self._select_action.isChecked():
            return
        if not canvas.selected_entity_id:
            return
        canvas.clear_selected_entity()

    def _on_nudge_selected_entity(self, dx: int, dy: int) -> None:
        self._nudge_selected_entity_impl(dx, dy, screen_only=False)

    def _on_nudge_screen_entity(self, dx: int, dy: int) -> None:
        self._nudge_selected_entity_impl(dx, dy, screen_only=True)

    def _nudge_selected_entity_impl(self, dx: int, dy: int, *, screen_only: bool) -> None:
        context = self._active_area_context()
        if context is None or not self._select_action.isChecked():
            return
        content_id, doc, canvas = context
        selected_id = canvas.selected_entity_id
        if not selected_id:
            return
        entity = entity_by_id(doc, selected_id)
        if entity is None:
            return
        effective_space = self._entity_effective_space(entity)
        if effective_space == "screen":
            if not move_entity_pixels(doc, selected_id, dx, dy):
                return
        else:
            if screen_only:
                return
            if not move_entity_by_id(doc, selected_id, dx, dy):
                return
        canvas.set_selected_entity(selected_id, cycle_position=1, cycle_total=1, emit=False)
        self._set_render_target_entity(selected_id)
        canvas.refresh_scene_contents()
        self._tab_widget.set_dirty(content_id, True)
        self._update_paint_status()
        entity = entity_by_id(doc, selected_id)
        if entity is None:
            return
        if effective_space == "screen":
            self.statusBar().showMessage(
                f"Moved {selected_id} to pixel ({entity.pixel_x or 0}, {entity.pixel_y or 0}).",
                2500,
            )
            return
        self.statusBar().showMessage(
            f"Moved {selected_id} to grid ({entity.grid_x}, {entity.grid_y}).",
            2500,
        )

    def _on_apply_entity_instance_json(self) -> None:
        context = self._active_area_context()
        entity_id = self._active_instance_entity_id
        if context is None or entity_id is None:
            return
        content_id, doc, canvas = context
        current = entity_by_id(doc, entity_id)
        if current is None:
            return
        try:
            raw = json.loads(self._entity_instance_panel.json_text)
        except Exception as exc:
            QMessageBox.warning(self, "Invalid JSON", f"Could not parse entity JSON:\n{exc}")
            return
        if not isinstance(raw, dict):
            QMessageBox.warning(self, "Invalid Entity", "Entity instance JSON must be an object.")
            return
        updated = EntityDocument.from_dict(raw)
        if not self._apply_entity_instance_update(
            content_id,
            doc,
            canvas,
            current,
            updated,
            status_message=f"Applied JSON changes to entity {updated.id}.",
        ):
            return

    def _on_revert_entity_instance_json(self) -> None:
        self._refresh_entity_instance_panel()
        self.statusBar().showMessage("Reverted selected entity JSON.", 2000)

    def _on_apply_entity_instance_fields(self) -> None:
        context = self._active_area_context()
        entity_id = self._active_instance_entity_id
        if context is None or entity_id is None:
            return
        content_id, doc, canvas = context
        current = entity_by_id(doc, entity_id)
        if current is None:
            return
        try:
            updated = self._entity_instance_panel.build_entity_from_fields()
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Invalid Entity",
                f"Could not build entity fields:\n{exc}",
            )
            return
        updated.render_order = current.render_order
        updated.y_sort = current.y_sort
        updated.sort_y_offset = current.sort_y_offset
        updated.stack_order = current.stack_order
        if not self._apply_entity_instance_update(
            content_id,
            doc,
            canvas,
            current,
            updated,
            status_message=f"Applied field changes to entity {updated.id}.",
        ):
            return

    def _on_revert_entity_instance_fields(self) -> None:
        self._refresh_entity_instance_panel()
        self.statusBar().showMessage("Reverted selected entity fields.", 2000)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _open_area(self, area_id: str, file_path: Path) -> None:
        """Open an area in a tab (or focus existing tab)."""
        if self._catalog is None:
            return

        # If already open, just focus
        if area_id in self._area_docs:
            self._tab_widget.open_tab(area_id, file_path, ContentType.AREA)
            return

        try:
            doc = load_area_document(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to load area:\n{exc}")
            return

        self._area_docs[area_id] = doc

        canvas = TileCanvas()
        canvas.set_area(
            doc,
            self._catalog,
            self._templates,
            display_size=(self._display_width, self._display_height),
        )
        canvas.set_grid_visible(self._grid_action.isChecked())

        self._tab_widget.open_tab(
            area_id, file_path, ContentType.AREA, widget=canvas
        )
        self._connect_canvas(canvas)
        self._area_panel.highlight_area(area_id)

    def _active_canvas(self) -> TileCanvas | None:
        """Return the TileCanvas of the active tab, if it's an area tab."""
        widget = self._tab_widget.active_widget()
        if isinstance(widget, TileCanvas):
            return widget
        return None

    def _connect_canvas(self, canvas: TileCanvas) -> None:
        """Wire a canvas's signals to status bar and layer panel.

        Uses unique connections to avoid duplicates when switching tabs.
        """
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            if self._connected_canvas is not None:
                try:
                    self._connected_canvas.cell_hovered.disconnect(
                        self._on_cell_hovered
                    )
                except (RuntimeError, TypeError):
                    pass
                try:
                    self._connected_canvas.screen_pixel_hovered.disconnect(
                        self._on_screen_pixel_hovered
                    )
                except (RuntimeError, TypeError):
                    pass
                try:
                    self._connected_canvas.zoom_changed.disconnect(
                        self._on_zoom_changed
                    )
                except (RuntimeError, TypeError):
                    pass
                try:
                    self._connected_canvas.cell_flag_edited.disconnect(
                        self._on_cell_flag_edited
                    )
                except (RuntimeError, TypeError):
                    pass
                try:
                    self._connected_canvas.tile_painted.disconnect(
                        self._on_tile_painted
                    )
                except (RuntimeError, TypeError):
                    pass
                try:
                    self._connected_canvas.tile_eyedropped.disconnect(
                        self._on_tile_eyedropped
                    )
                except (RuntimeError, TypeError):
                    pass
                try:
                    self._connected_canvas.entity_paint_requested.disconnect(
                        self._on_entity_paint_requested
                    )
                except (RuntimeError, TypeError):
                    pass
                try:
                    self._connected_canvas.entity_screen_paint_requested.disconnect(
                        self._on_entity_screen_paint_requested
                    )
                except (RuntimeError, TypeError):
                    pass
                try:
                    self._connected_canvas.entity_delete_requested.disconnect(
                        self._on_entity_delete_requested
                    )
                except (RuntimeError, TypeError):
                    pass
                try:
                    self._connected_canvas.entity_selection_changed.disconnect(
                        self._on_entity_selection_changed
                    )
                except (RuntimeError, TypeError):
                    pass
            try:
                self._layer_panel.layer_visibility_changed.disconnect()
            except (RuntimeError, TypeError):
                pass
            try:
                self._layer_panel.entities_visibility_changed.disconnect()
            except (RuntimeError, TypeError):
                pass

        self._connected_canvas = canvas
        canvas.cell_hovered.connect(self._on_cell_hovered)
        canvas.screen_pixel_hovered.connect(self._on_screen_pixel_hovered)
        canvas.zoom_changed.connect(self._on_zoom_changed)
        canvas.cell_flag_edited.connect(self._on_cell_flag_edited)
        canvas.tile_painted.connect(self._on_tile_painted)
        canvas.tile_eyedropped.connect(self._on_tile_eyedropped)
        canvas.entity_paint_requested.connect(self._on_entity_paint_requested)
        canvas.entity_screen_paint_requested.connect(
            self._on_entity_screen_paint_requested
        )
        canvas.entity_delete_requested.connect(self._on_entity_delete_requested)
        canvas.entity_selection_changed.connect(self._on_entity_selection_changed)
        self._layer_panel.layer_visibility_changed.connect(canvas.set_layer_visible)
        self._layer_panel.entities_visibility_changed.connect(
            canvas.set_entities_visible
        )

    def _entity_effective_space(self, entity: EntityDocument) -> str:
        """Return one entity's effective space using template fallback."""
        if entity.space != "world":
            return entity.space
        if entity.template and self._templates is not None:
            template_space = self._templates.get_template_space(entity.template)
            if template_space is not None:
                return template_space
        return entity.space

    def _entity_template_space(self, template_id: str) -> str:
        if self._templates is not None:
            template_space = self._templates.get_template_space(template_id)
            if template_space is not None:
                return template_space
        return "world"

    def _screen_space_entity_ids(self, doc: AreaDocument) -> set[str]:
        return {
            entity.id
            for entity in doc.entities
            if self._entity_effective_space(entity) == "screen"
        }

    def _project_entity_id_usages(self) -> list[_EntityIdUsage]:
        if self._manifest is None:
            return []

        usages: list[_EntityIdUsage] = []
        area_entries = discover_areas(self._manifest)
        seen_area_ids: set[str] = set()
        for entry in area_entries:
            seen_area_ids.add(entry.area_id)
            document = self._area_docs.get(entry.area_id)
            if document is None:
                try:
                    document = load_area_document(entry.file_path)
                except Exception as exc:
                    log.warning("Failed to scan area entity ids for %s: %s", entry.area_id, exc)
                    continue
            for entity in document.entities:
                entity_id = str(entity.id).strip()
                if not entity_id:
                    continue
                usages.append(
                    _EntityIdUsage(
                        entity_id=entity_id,
                        kind="area_entity",
                        area_id=entry.area_id,
                        file_path=entry.file_path,
                    )
                )

        for area_id, document in self._area_docs.items():
            if area_id in seen_area_ids:
                continue
            info = self._tab_widget.content_info(area_id)
            file_path = info.file_path if info is not None else None
            for entity in document.entities:
                entity_id = str(entity.id).strip()
                if not entity_id:
                    continue
                usages.append(
                    _EntityIdUsage(
                        entity_id=entity_id,
                        kind="area_entity",
                        area_id=area_id,
                        file_path=file_path,
                    )
                )

        for entry in discover_global_entities(self._manifest):
            entity_id = str(entry.entity_id).strip()
            if not entity_id or entity_id.startswith("<unnamed #"):
                continue
            usages.append(_EntityIdUsage(entity_id=entity_id, kind="global_entity"))
        return usages

    def _project_used_entity_ids(self) -> set[str]:
        return {usage.entity_id for usage in self._project_entity_id_usages()}

    def _generate_project_unique_entity_id(
        self,
        doc: AreaDocument,
        template_id: str,
    ) -> str:
        from area_editor.operations.entities import generate_entity_id

        return generate_entity_id(
            doc,
            template_id,
            existing_ids=self._project_used_entity_ids(),
        )

    def _find_project_entity_id_conflict(
        self,
        entity_id: str,
        *,
        current_area_id: str,
        current_entity_id: str | None = None,
    ) -> _EntityIdUsage | None:
        resolved_entity_id = str(entity_id).strip()
        if not resolved_entity_id:
            return None
        for usage in self._project_entity_id_usages():
            if usage.entity_id != resolved_entity_id:
                continue
            if (
                usage.kind == "area_entity"
                and usage.area_id == current_area_id
                and current_entity_id is not None
                and resolved_entity_id == current_entity_id
            ):
                continue
            return usage
        return None

    @staticmethod
    def _describe_entity_id_usage(usage: _EntityIdUsage) -> str:
        if usage.kind == "global_entity":
            return "a project global entity"
        if usage.area_id:
            return f"area '{usage.area_id}'"
        return "another area entity"

    def _delete_world_entity_at(self, doc: AreaDocument, col: int, row: int) -> str | None:
        """Delete the topmost effective world-space entity at one grid cell."""
        matches = [
            entity
            for entity in doc.entities
            if self._entity_effective_space(entity) != "screen" and entity.x == col and entity.y == row
        ]
        if not matches:
            return None
        topmost = max(matches, key=self._world_entity_sort_key)
        return delete_entity_by_id(doc, topmost.id)

    @staticmethod
    def _world_entity_sort_key(entity: EntityDocument) -> tuple:
        sort_bucket = 1 if entity.y_sort else 0
        sort_y = float(entity.y + 1 + entity.sort_y_offset) if entity.y_sort else 0.0
        return (
            entity.render_order,
            sort_bucket,
            sort_y,
            entity.stack_order,
            entity.x,
            entity.id,
        )

    def _populate_asset_context_menu(
        self,
        menu,
        _content_id: str,
        file_path: Path,
    ) -> None:
        if file_path.suffix.lower() not in _IMAGE_SUFFIXES:
            return
        menu.addSeparator()
        add_action = QAction("Add Tileset To Active Area...", self)
        add_action.setEnabled(self._active_area_context() is not None)
        add_action.triggered.connect(
            lambda: self._add_tileset_to_active_area(file_path=file_path)
        )
        menu.addAction(add_action)

    def _add_tileset_to_active_area(self, file_path: Path | None = None) -> None:
        context = self._active_area_context()
        if context is None or self._catalog is None:
            QMessageBox.information(
                self,
                "No Active Area",
                "Open an area tab before adding a tileset.",
            )
            return

        content_id, doc, canvas = context
        authored_path = (
            self._authored_asset_path_for(file_path) if file_path is not None else None
        )
        details = self._show_tileset_details_dialog(
            path_value=authored_path or "",
            tile_width=doc.tile_size or 16,
            tile_height=doc.tile_size or 16,
            allow_path_edit=file_path is None,
        )
        if details is None:
            return

        authored_path, tile_width, tile_height = details
        frame_count = self._catalog.get_frame_count(authored_path, tile_width, tile_height)
        if frame_count <= 0:
            QMessageBox.warning(
                self,
                "Invalid Tileset",
                "The selected image could not be sliced into any whole tiles.",
            )
            return

        existing_counts = self._current_tileset_counts(doc)
        tileset = append_tileset(
            doc,
            authored_path,
            tile_width,
            tile_height,
            existing_tile_counts=existing_counts,
        )
        canvas.set_tileset_index_hint(len(doc.tilesets) - 1)
        canvas.set_selected_gid(0)
        canvas.set_brush_erase_mode(True)
        self._tab_widget.set_dirty(content_id, True)
        self._tileset_panel.set_tilesets(
            doc.tilesets,
            self._catalog,
            current_index=len(doc.tilesets) - 1,
            selected_gid=0,
            erase_mode=True,
        )
        self._paint_tiles_action.setEnabled(bool(doc.tile_layers and doc.tilesets))
        self.statusBar().showMessage(
            f"Added tileset {Path(tileset.path).stem} to {content_id}.",
            3000,
        )

    def _edit_tileset_in_active_area(self, index: int) -> None:
        context = self._active_area_context()
        if context is None or self._catalog is None:
            return

        content_id, doc, canvas = context
        if index < 0 or index >= len(doc.tilesets):
            return
        tileset = doc.tilesets[index]
        details = self._show_tileset_details_dialog(
            path_value=tileset.path,
            tile_width=tileset.tile_width,
            tile_height=tileset.tile_height,
            allow_path_edit=False,
        )
        if details is None:
            return

        _path_value, tile_width, tile_height = details
        frame_count = self._catalog.get_frame_count(tileset.path, tile_width, tile_height)
        if frame_count <= 0:
            QMessageBox.warning(
                self,
                "Invalid Tile Size",
                "Those dimensions produce zero whole tiles for this image.",
            )
            return

        if not update_tileset_dimensions(doc, index, tile_width, tile_height):
            return

        canvas.set_tileset_index_hint(index)
        self._tab_widget.set_dirty(content_id, True)
        self._tileset_panel.set_tilesets(
            doc.tilesets,
            self._catalog,
            current_index=index,
            selected_gid=canvas.selected_gid,
            erase_mode=canvas.brush_erase_mode,
        )
        self.statusBar().showMessage(
            f"Updated tile size for {Path(tileset.path).stem}.",
            3000,
        )

    def _show_tileset_details_dialog(
        self,
        *,
        path_value: str,
        tile_width: int,
        tile_height: int,
        allow_path_edit: bool,
    ) -> tuple[str, int, int] | None:
        dialog = _TilesetDetailsDialog(
            self,
            path_value=path_value,
            tile_width=tile_width,
            tile_height=tile_height,
            allow_path_edit=allow_path_edit,
            browse_callback=self._browse_project_asset if allow_path_edit else None,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        authored_path = dialog.authored_path
        if not authored_path:
            QMessageBox.warning(self, "Missing Path", "Choose an asset image first.")
            return None
        return authored_path, dialog.tile_width, dialog.tile_height

    def _browse_project_asset(self) -> str | None:
        if self._manifest is None:
            return None
        start_dir = str(self._manifest.asset_paths[0]) if self._manifest.asset_paths else str(
            self._manifest.project_root
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Tileset Image",
            start_dir,
            "Image files (*.png *.webp *.bmp *.jpg *.jpeg);;All files (*)",
        )
        if not path:
            return None
        return self._authored_asset_path_for(Path(path))

    def _authored_asset_path_for(self, file_path: Path | None) -> str | None:
        if self._manifest is None or file_path is None:
            return None
        resolved = file_path.resolve()
        for asset_dir in self._manifest.asset_paths:
            try:
                return str(resolved.relative_to(asset_dir.parent.resolve())).replace("\\", "/")
            except ValueError:
                pass
            try:
                return str(resolved.relative_to(asset_dir.resolve())).replace("\\", "/")
            except ValueError:
                pass
        try:
            return str(resolved.relative_to(self._manifest.project_root)).replace("\\", "/")
        except ValueError:
            return None

    def _active_area_context(self) -> tuple[str, AreaDocument, TileCanvas] | None:
        info = self._tab_widget.active_info()
        canvas = self._active_canvas()
        if info is None or info.content_type != ContentType.AREA or canvas is None:
            return None
        document = self._area_docs.get(info.content_id)
        if document is None:
            return None
        return info.content_id, document, canvas

    def _current_tileset_counts(self, document: AreaDocument) -> list[int]:
        if self._catalog is None:
            return [0 for _ in document.tilesets]
        return [self._catalog.get_tileset_frame_count(ts) for ts in document.tilesets]

    def _size_to_screen(self) -> None:
        """Set initial window size to ~80% of the primary screen."""
        try:
            from PySide6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            if screen:
                geom = screen.availableGeometry()
                w = int(geom.width() * 0.8)
                h = int(geom.height() * 0.8)
                self.resize(w, h)
                # Centre on screen
                x = geom.x() + (geom.width() - w) // 2
                y = geom.y() + (geom.height() - h) // 2
                self.move(x, y)
        except Exception:
            self.resize(1280, 900)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._maybe_save_dirty_tabs():
            event.accept()
            return
        event.ignore()

    def _save_area(self, content_id: str) -> bool:
        info = self._tab_widget.content_info(content_id)
        document = self._area_docs.get(content_id)
        if info is None or document is None:
            return True
        try:
            save_area_document(info.file_path, document)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Failed to save {content_id}:\n{exc}",
            )
            return False
        self._tab_widget.set_dirty(content_id, False)
        return True

    def _save_content(self, content_id: str) -> bool:
        info = self._tab_widget.content_info(content_id)
        if info is None:
            return True
        if info.content_type == ContentType.AREA:
            return self._save_area(content_id)

        widget = self._tab_widget.widget_for_content(content_id)
        if not isinstance(
            widget,
            (
                JsonViewerWidget,
                GlobalEntitiesEditorWidget,
                EntityTemplateEditorWidget,
                ItemEditorWidget,
            ),
        ):
            return True
        try:
            widget.save_to_file()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Failed to save {content_id}:\n{exc}",
            )
            return False
        self._tab_widget.set_dirty(content_id, False)
        if info.content_type in {
            ContentType.PROJECT_MANIFEST,
            ContentType.SHARED_VARIABLES,
            ContentType.GLOBAL_ENTITIES,
        }:
            self._refresh_project_metadata_surfaces()
        elif info.content_type == ContentType.ENTITY_TEMPLATE:
            self._refresh_template_surfaces()
        return True

    def _maybe_save_dirty_tabs(self, content_ids: list[str] | None = None) -> bool:
        dirty_ids = self._tab_widget.dirty_content_ids()
        if content_ids is not None:
            wanted = set(content_ids)
            dirty_ids = [content_id for content_id in dirty_ids if content_id in wanted]
        if not dirty_ids:
            return True

        message = (
            f"Save changes to {dirty_ids[0]} before continuing?"
            if len(dirty_ids) == 1
            else f"Save changes to {len(dirty_ids)} edited areas before continuing?"
        )
        choice = QMessageBox.question(
            self,
            "Unsaved Changes",
            message,
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        if choice == QMessageBox.StandardButton.Discard:
            return True
        for content_id in dirty_ids:
            if not self._save_content(content_id):
                return False
        return True

    def _on_tile_painted(self, layer_idx: int, col: int, row: int, gid: int) -> None:
        info = self._tab_widget.active_info()
        if info is None or info.content_type != ContentType.AREA:
            return
        self._tab_widget.set_dirty(info.content_id, True)

    def _on_tile_eyedropped(self, gid: int) -> None:
        self._tileset_panel.select_gid(gid)
        canvas = self._active_canvas()
        if canvas is not None:
            canvas.set_selected_gid(gid)
            canvas.set_tileset_index_hint(self._tileset_panel.current_tileset_index)
            canvas.set_brush_erase_mode(self._tileset_panel.brush_is_erase)
            canvas.set_active_brush_type(
                BrushType.ERASER if self._tileset_panel.brush_is_erase else BrushType.TILE
            )
        self._active_brush_type = (
            BrushType.ERASER if self._tileset_panel.brush_is_erase else BrushType.TILE
        )
        self._tileset_panel.set_brush_active(True)
        self._template_panel.set_brush_active(None)
        self._update_paint_status()

    def _update_paint_status(self) -> None:
        """Update status bar with current tool info."""
        if self._select_action.isChecked():
            self._status_layer.setText("")
            self._status_gid.setText(self._selection_status_text())
            return

        if self._active_brush_type in {BrushType.TILE, BrushType.ERASER}:
            self._status_layer.setText(f"Layer: {self._layer_panel.active_layer_name()}")
        else:
            self._status_layer.setText("")

        if self._active_brush_type == BrushType.ENTITY:
            if self._entity_brush_template_id is None:
                self._status_gid.setText("(no brush)")
                return
            self._status_gid.setText(
                f"Paint: entity {self._entity_brush_template_id.rsplit('/', 1)[-1]}"
            )
            return

        if self._active_brush_type == BrushType.ERASER:
            self._status_gid.setText("Erase")
            return

        gid = self._tileset_panel.selected_gid
        self._status_gid.setText(f"Paint: tile GID {gid}" if gid else "(no brush)")

    def _set_cell_flags_action_state(self, enabled: bool) -> None:
        self._cell_flags_action.blockSignals(True)
        self._cell_flags_action.setChecked(enabled)
        self._cell_flags_action.blockSignals(False)

    def _set_paint_tiles_action_state(self, enabled: bool) -> None:
        self._paint_tiles_action.blockSignals(True)
        self._paint_tiles_action.setChecked(enabled)
        self._paint_tiles_action.blockSignals(False)

    def _set_select_action_state(self, enabled: bool) -> None:
        self._select_action.blockSignals(True)
        self._select_action.setChecked(enabled)
        self._select_action.blockSignals(False)

    def _set_json_editing_action_state(self, enabled: bool) -> None:
        self._enable_json_editing_action.blockSignals(True)
        self._enable_json_editing_action.setChecked(enabled)
        self._enable_json_editing_action.blockSignals(False)

    def _ensure_paint_mode(self) -> None:
        """Turn on the shared Paint tool after an explicit brush selection."""
        canvas = self._active_canvas()
        if canvas is None or not self._paint_tiles_action.isEnabled():
            return
        if self._paint_tiles_action.isChecked() and canvas.tile_paint_mode:
            return
        self._set_paint_tiles_action_state(True)
        self._on_paint_tiles_toggled(True)

    def _apply_active_brush_to_canvas(self, canvas: TileCanvas) -> None:
        self._apply_entity_brush_to_canvas(canvas)
        canvas.set_selected_gid(self._tileset_panel.selected_gid)
        canvas.set_brush_erase_mode(self._tileset_panel.brush_is_erase)
        canvas.set_active_brush_type(self._active_brush_type)
        self._tileset_panel.set_brush_active(self._active_brush_type != BrushType.ENTITY)
        self._template_panel.set_brush_active(
            self._entity_brush_template_id if self._active_brush_type == BrushType.ENTITY else None
        )

    def _set_render_target_layer(self, index: int) -> None:
        self._render_target_kind = "layer"
        self._render_target_ref = index
        self._refresh_render_properties_target()

    def _set_render_target_entity(self, entity_id: str) -> None:
        self._render_target_kind = "entity"
        self._render_target_ref = entity_id
        self._refresh_render_properties_target()

    def _refresh_render_properties_target(self) -> None:
        context = self._active_area_context()
        if context is None:
            self._render_panel.clear_target()
            return
        _content_id, doc, _canvas = context

        if self._render_target_kind == "entity" and isinstance(self._render_target_ref, str):
            entity = entity_by_id(doc, self._render_target_ref)
            if entity is not None:
                label = f"Entity {entity.id}"
                if entity.template:
                    label += f" [{entity.template.rsplit('/', 1)[-1]}]"
                self._render_panel.set_target(
                    label=label,
                    render_order=entity.render_order,
                    y_sort=entity.y_sort,
                    sort_y_offset=entity.sort_y_offset,
                    stack_order=entity.stack_order,
                )
                return

        index = self._render_target_ref if isinstance(self._render_target_ref, int) else self._layer_panel.active_layer
        if 0 <= index < len(doc.tile_layers):
            layer = doc.tile_layers[index]
            self._render_target_kind = "layer"
            self._render_target_ref = index
            self._render_panel.set_target(
                label=f"Layer {layer.name}",
                render_order=layer.render_order,
                y_sort=layer.y_sort,
                sort_y_offset=layer.sort_y_offset,
                stack_order=layer.stack_order,
            )
            return

        self._render_target_kind = None
        self._render_target_ref = None
        self._render_panel.clear_target()

    def _refresh_entity_instance_panel(self) -> None:
        context = self._active_area_context()
        if context is None or self._active_instance_entity_id is None:
            self._entity_instance_panel.clear_entity()
            return
        _content_id, doc, _canvas = context
        entity = entity_by_id(doc, self._active_instance_entity_id)
        if entity is None:
            self._active_instance_entity_id = None
            self._entity_instance_panel.clear_entity()
            return
        self._entity_instance_panel.set_area_bounds(doc.width, doc.height)
        self._entity_instance_panel.load_entity(entity)

    def _prepare_for_entity_instance_target_change(self, new_entity_id: str | None) -> bool:
        if not self._entity_instance_panel.is_dirty and not self._entity_instance_panel.fields_dirty:
            return True
        if new_entity_id == self._entity_instance_panel.entity_id:
            return True
        tab_name = "JSON"
        apply_handler = self._on_apply_entity_instance_json
        dirty_check = lambda: self._entity_instance_panel.is_dirty
        if self._entity_instance_panel.fields_dirty:
            tab_name = "Fields"
            apply_handler = self._on_apply_entity_instance_fields
            dirty_check = lambda: self._entity_instance_panel.fields_dirty
        choice = QMessageBox.question(
            self,
            f"Unsaved Entity {tab_name}",
            f"Apply changes in the {tab_name} tab before switching?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        if choice == QMessageBox.StandardButton.Save:
            apply_handler()
            return not dirty_check()
        return True

    def _apply_entity_instance_update(
        self,
        content_id: str,
        doc: AreaDocument,
        canvas: TileCanvas,
        current: EntityDocument,
        updated: EntityDocument,
        *,
        status_message: str,
    ) -> bool:
        error = self._validate_entity_update(content_id, doc, current, updated)
        if error is not None:
            title, message = error
            QMessageBox.warning(self, title, message)
            return False
        index = doc.entities.index(current)
        was_selected = (
            canvas.selected_entity_id == current.id
            or self._active_instance_entity_id == current.id
        )
        doc.entities[index] = updated
        self._active_instance_entity_id = updated.id
        canvas.refresh_scene_contents()
        if was_selected:
            canvas.set_selected_entity(
                updated.id,
                cycle_position=1,
                cycle_total=1,
                emit=False,
            )
        self._tab_widget.set_dirty(content_id, True)
        self._refresh_render_properties_target()
        self._refresh_entity_instance_panel()
        self._sync_json_edit_actions()
        self._update_paint_status()
        self.statusBar().showMessage(status_message, 2500)
        return True

    def _validate_entity_update(
        self,
        content_id: str,
        doc: AreaDocument,
        current: EntityDocument,
        updated: EntityDocument,
    ) -> tuple[str, str] | None:
        if not updated.id:
            return "Invalid Entity", "Entity instance must have a non-empty id."
        if updated.space == "world" and not (
            0 <= updated.x < doc.width and 0 <= updated.y < doc.height
        ):
            return (
                "Invalid Position",
                f"World-space entity position must stay inside the area bounds "
                f"(0..{doc.width - 1}, 0..{doc.height - 1}).",
            )
        for other in doc.entities:
            if other is current:
                continue
            if other.id == updated.id:
                return (
                    "Duplicate Entity ID",
                    f"Another entity already uses id '{updated.id}'.",
                )
        conflict = self._find_project_entity_id_conflict(
            updated.id,
            current_area_id=content_id,
            current_entity_id=current.id,
        )
        if conflict is not None:
            return (
                "Duplicate Entity ID",
                f"Entity id '{updated.id}' is already used by "
                f"{self._describe_entity_id_usage(conflict)}.",
            )
        return None

    def _active_json_widget(
        self,
    ) -> (
        JsonViewerWidget
        | GlobalEntitiesEditorWidget
        | EntityTemplateEditorWidget
        | ItemEditorWidget
        | None
    ):
        widget = self._tab_widget.active_widget()
        if isinstance(
            widget,
            (
                JsonViewerWidget,
                GlobalEntitiesEditorWidget,
                EntityTemplateEditorWidget,
                ItemEditorWidget,
            ),
        ):
            return widget
        return None

    def _sync_json_edit_actions(self) -> None:
        self._set_json_editing_action_state(self._json_editing_enabled)
        self._apply_json_editing_state()

    def _apply_json_editing_state(self) -> None:
        json_widget = self._active_json_widget()
        if json_widget is not None:
            json_widget.set_editing_enabled(self._json_editing_enabled)
        self._entity_instance_panel.set_editing_enabled(self._json_editing_enabled)

    def _selection_status_text(self) -> str:
        context = self._active_area_context()
        if context is None:
            return "Select: none"
        _content_id, doc, canvas = context
        if not canvas.selected_entity_id:
            return "Select: none"
        entity = entity_by_id(doc, canvas.selected_entity_id)
        if entity is None:
            return "Select: none"
        template = entity.template.rsplit("/", 1)[-1] if entity.template else "entity"
        detail = ""
        if canvas.selected_entity_cycle_total > 1:
            detail = (
                f" ({canvas.selected_entity_cycle_position}"
                f" of {canvas.selected_entity_cycle_total})"
            )
        return f"Select: {entity.id} [{template}]{detail}"

    def _apply_entity_brush_to_canvas(self, canvas: TileCanvas) -> None:
        if self._entity_brush_template_id is None:
            canvas.clear_entity_brush()
            self._entity_brush_supported = False
            return
        target_space = self._entity_template_space(self._entity_brush_template_id)
        supported = True
        canvas.set_entity_brush(
            self._entity_brush_template_id,
            self._entity_brush_preview(self._entity_brush_template_id),
            supported=supported,
            target_space=target_space,
        )
        self._entity_brush_supported = supported

    def _entity_template_is_world_space(self, template_id: str) -> bool:
        if self._templates is None:
            return False
        return self._templates.get_template_space(template_id) != "screen"

    def _entity_render_order(self, template_id: str) -> int:
        if self._templates is None:
            return 10
        value = self._templates.get_template_render_order(template_id)
        return 10 if value is None else value

    def _entity_brush_preview(self, template_id: str):
        if self._templates is None or self._catalog is None:
            return None
        visual = self._templates.get_first_visual(template_id)
        if visual is None:
            return None
        frame_index = visual.frames[0] if visual.frames else 0
        return self._catalog.get_sprite_frame(
            visual.path,
            visual.frame_width,
            visual.frame_height,
            frame_index,
        )
