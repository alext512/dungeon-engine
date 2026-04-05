"""Main application window.

Hosts a tabbed document area as the central widget and docks content
browser panels on the left and the layer panel on the right.  Wires
menus, status bar, and cross-widget signals.
"""

from __future__ import annotations

import copy
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
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
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
from area_editor.json_format import format_json_for_editor
from area_editor.project_io.asset_resolver import AssetResolver
from area_editor.project_io.manifest import (
    AREA_ID_PREFIX,
    ProjectManifest,
    discover_areas,
    discover_entity_templates,
    discover_global_entities,
    discover_items,
    load_manifest,
)
from area_editor.operations.areas import (
    add_columns_left,
    add_columns_right,
    add_rows_above,
    add_rows_below,
    add_tile_layer,
    can_remove_bottom_rows,
    can_remove_left_columns,
    can_remove_right_columns,
    can_remove_top_rows,
    layer_dimensions,
    make_empty_area_document,
    move_tile_layer,
    remove_bottom_rows,
    remove_left_columns,
    remove_right_columns,
    remove_top_rows,
    remove_tile_layer,
    rename_tile_layer,
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
from area_editor.widgets.browser_workspace_dock import BrowserWorkspaceDock
from area_editor.widgets.document_tab_widget import ContentType, DocumentTabWidget
from area_editor.widgets.entity_instance_json_panel import EntityInstanceJsonPanel
from area_editor.widgets.entity_template_editor_widget import EntityTemplateEditorWidget
from area_editor.widgets.file_tree_panel import FileTreePanel
from area_editor.widgets.global_entities_editor_widget import GlobalEntitiesEditorWidget
from area_editor.widgets.global_entities_panel import GlobalEntitiesPanel
from area_editor.widgets.item_editor_widget import ItemEditorWidget
from area_editor.widgets.json_viewer_widget import JsonViewerWidget
from area_editor.widgets.layer_list_panel import LayerListPanel
from area_editor.widgets.project_manifest_editor_widget import ProjectManifestEditorWidget
from area_editor.widgets.render_properties_panel import RenderPropertiesPanel
from area_editor.widgets.shared_variables_editor_widget import SharedVariablesEditorWidget
from area_editor.widgets.template_list_panel import TemplateListPanel
from area_editor.widgets.tile_canvas import BrushType, TileCanvas
from area_editor.widgets.tileset_browser_panel import TilesetBrowserPanel

_SETTINGS_KEY_LAST_PROJECT = "last_project_path"
_SETTINGS_KEY_JSON_EDITING_ENABLED = "json_editing_enabled"
_IMAGE_SUFFIXES = {".png", ".webp", ".bmp", ".jpg", ".jpeg"}
_COMMAND_ID_PREFIX = "commands"
_DIALOGUE_ID_PREFIX = "dialogues"
_AREA_DUPLICATE_FULL = "Full Copy"
_AREA_DUPLICATE_LAYOUT = "Layout Copy"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _EntityIdUsage:
    entity_id: str
    kind: str
    area_id: str | None = None
    file_path: Path | None = None


@dataclass(frozen=True)
class _JsonReferenceFileUpdate:
    file_path: Path
    updated_text: str
    changed_paths: tuple[str, ...]


@dataclass(frozen=True)
class _JsonReferenceUsage:
    file_path: Path
    matched_paths: tuple[str, ...]


@dataclass(frozen=True)
class _TileClipboard:
    width: int
    height: int
    grid: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class _ReferenceKeyMatcher:
    exact_keys: frozenset[str]
    suffix_keys: frozenset[str] = frozenset()

    def matches(self, key: str) -> bool:
        return key in self.exact_keys or any(
            key.endswith(suffix) for suffix in self.suffix_keys
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
        self._entities_visible: bool = True
        self._tile_clipboard: _TileClipboard | None = None

        # Central tabbed document area
        self._tab_widget = DocumentTabWidget()
        self.setCentralWidget(self._tab_widget)

        # Dock panels — left side: project content browser tabs
        self._area_panel = AreaListPanel()
        self._template_panel = TemplateListPanel()

        self._item_panel = FileTreePanel(
            "Items",
            object_name="ItemPanel",
            content_prefix="items",
        )
        self._global_entities_panel = GlobalEntitiesPanel()

        self._dialogue_panel = FileTreePanel(
            "Dialogues",
            object_name="DialoguePanel",
            content_prefix=_DIALOGUE_ID_PREFIX,
        )
        self._command_panel = FileTreePanel(
            "Commands",
            object_name="CommandPanel",
            content_prefix=_COMMAND_ID_PREFIX,
        )

        self._asset_panel = FileTreePanel(
            "Assets",
            object_name="AssetPanel",
            file_extensions=(),  # show all file types
            preserve_file_extensions=True,
        )
        self._browser_workspace = BrowserWorkspaceDock()
        self._browser_workspace.add_page(
            row=1,
            key="areas",
            title="Areas",
            widget=self._extract_dock_content(self._area_panel),
        )
        self._browser_workspace.add_page(
            row=1,
            key="templates",
            title="Entity Templates",
            widget=self._extract_dock_content(self._template_panel),
        )
        self._browser_workspace.add_page(
            row=1,
            key="items",
            title="Items",
            widget=self._extract_dock_content(self._item_panel),
        )
        self._browser_workspace.add_page(
            row=1,
            key="globals",
            title="Global Entities",
            widget=self._extract_dock_content(self._global_entities_panel),
        )
        self._browser_workspace.add_page(
            row=2,
            key="dialogues",
            title="Dialogues",
            widget=self._extract_dock_content(self._dialogue_panel),
        )
        self._browser_workspace.add_page(
            row=2,
            key="commands",
            title="Commands",
            widget=self._extract_dock_content(self._command_panel),
        )
        self._browser_workspace.add_page(
            row=2,
            key="assets",
            title="Assets",
            widget=self._extract_dock_content(self._asset_panel),
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._browser_workspace)

        # Right side: layer panel + tileset browser
        self._layer_panel = LayerListPanel()
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._layer_panel)

        self._render_panel = RenderPropertiesPanel()
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._render_panel)

        self._entity_instance_panel = EntityInstanceJsonPanel()
        self._entity_instance_panel.set_reference_picker_callbacks(
            area_picker=self._browse_project_area_id,
            entity_picker=self._browse_project_entity_id,
            item_picker=self._browse_project_item_id,
            dialogue_picker=self._browse_project_dialogue_id,
            command_picker=self._browse_project_command_id,
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._entity_instance_panel)

        self._tileset_panel = TilesetBrowserPanel()
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._tileset_panel)

        # Build the left side as one browser stack on top plus a separate
        # entity-instance dock below it.
        self.splitDockWidget(self._browser_workspace, self._entity_instance_panel, Qt.Orientation.Vertical)
        self.resizeDocks(
            [self._browser_workspace, self._entity_instance_panel],
            [430, 240],
            Qt.Orientation.Vertical,
        )
        self.resizeDocks(
            [self._browser_workspace, self._layer_panel],
            [340, 320],
            Qt.Orientation.Horizontal,
        )
        self._browser_workspace.set_current_page("areas")

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
        self._area_panel.set_context_menu_builder(self._populate_area_context_menu)
        self._area_panel.set_folder_context_menu_builder(
            lambda menu, rel, path, root: self._populate_folder_context_menu(
                menu,
                ContentType.AREA,
                rel,
                path,
                root,
            )
        )
        self._area_panel.set_empty_space_context_menu_builder(
            lambda menu, roots, current_rel, current_path, current_root: self._populate_empty_space_context_menu(
                menu,
                ContentType.AREA,
                roots,
                current_rel,
                current_path,
                current_root,
            )
        )
        self._template_panel.set_context_menu_builder(self._populate_template_context_menu)
        self._template_panel.set_folder_context_menu_builder(
            lambda menu, rel, path, root: self._populate_folder_context_menu(
                menu,
                ContentType.ENTITY_TEMPLATE,
                rel,
                path,
                root,
            )
        )
        self._template_panel.set_empty_space_context_menu_builder(
            lambda menu, roots, current_rel, current_path, current_root: self._populate_empty_space_context_menu(
                menu,
                ContentType.ENTITY_TEMPLATE,
                roots,
                current_rel,
                current_path,
                current_root,
            )
        )
        self._item_panel.set_context_menu_builder(self._populate_item_context_menu)
        self._item_panel.set_folder_context_menu_builder(
            lambda menu, rel, path, root: self._populate_folder_context_menu(
                menu,
                ContentType.ITEM,
                rel,
                path,
                root,
            )
        )
        self._item_panel.set_empty_space_context_menu_builder(
            lambda menu, roots, current_rel, current_path, current_root: self._populate_empty_space_context_menu(
                menu,
                ContentType.ITEM,
                roots,
                current_rel,
                current_path,
                current_root,
            )
        )
        self._global_entities_panel.set_context_menu_builder(
            self._populate_global_entity_context_menu
        )
        self._dialogue_panel.set_context_menu_builder(self._populate_dialogue_context_menu)
        self._dialogue_panel.set_folder_context_menu_builder(
            lambda menu, rel, path, root: self._populate_folder_context_menu(
                menu,
                ContentType.DIALOGUE,
                rel,
                path,
                root,
            )
        )
        self._dialogue_panel.set_empty_space_context_menu_builder(
            lambda menu, roots, current_rel, current_path, current_root: self._populate_empty_space_context_menu(
                menu,
                ContentType.DIALOGUE,
                roots,
                current_rel,
                current_path,
                current_root,
            )
        )
        self._command_panel.set_context_menu_builder(self._populate_command_context_menu)
        self._command_panel.set_folder_context_menu_builder(
            lambda menu, rel, path, root: self._populate_folder_context_menu(
                menu,
                ContentType.NAMED_COMMAND,
                rel,
                path,
                root,
            )
        )
        self._command_panel.set_empty_space_context_menu_builder(
            lambda menu, roots, current_rel, current_path, current_root: self._populate_empty_space_context_menu(
                menu,
                ContentType.NAMED_COMMAND,
                roots,
                current_rel,
                current_path,
                current_root,
            )
        )
        self._asset_panel.set_context_menu_builder(self._populate_asset_context_menu)
        self._asset_panel.set_folder_context_menu_builder(
            lambda menu, rel, path, root: self._populate_folder_context_menu(
                menu,
                ContentType.ASSET,
                rel,
                path,
                root,
            )
        )
        self._asset_panel.set_empty_space_context_menu_builder(
            lambda menu, roots, current_rel, current_path, current_root: self._populate_empty_space_context_menu(
                menu,
                ContentType.ASSET,
                roots,
                current_rel,
                current_path,
                current_root,
            )
        )

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
        self._layer_panel.add_layer_requested.connect(self._on_add_tile_layer_requested)
        self._layer_panel.rename_layer_requested.connect(self._on_rename_tile_layer_requested)
        self._layer_panel.delete_layer_requested.connect(self._on_delete_tile_layer_requested)
        self._layer_panel.move_layer_up_requested.connect(
            lambda index: self._on_move_tile_layer_requested(index, -1)
        )
        self._layer_panel.move_layer_down_requested.connect(
            lambda index: self._on_move_tile_layer_requested(index, 1)
        )
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

    @staticmethod
    def _extract_dock_content(dock: QDockWidget) -> QWidget:
        widget = dock.widget()
        if widget is None:
            raise RuntimeError(f"Dock '{dock.objectName() or dock.windowTitle()}' has no content widget.")
        widget.setParent(None)
        return widget

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
        self._tile_clipboard = None
        self._layer_panel.clear_layers()
        self._render_panel.clear_target()
        self._entity_instance_panel.clear_entity()
        self._template_panel.set_brush_active(None)
        self._tileset_panel.clear_tilesets()
        self._entities_visibility_action.blockSignals(True)
        self._entities_visibility_action.setChecked(self._entities_visible)
        self._entities_visibility_action.blockSignals(False)
        self._sync_json_edit_actions()

        areas = discover_areas(self._manifest)
        self._area_panel.set_areas(areas, list(self._manifest.area_paths))
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

        self._tile_select_action = QAction("Tile &Select", self)
        self._tile_select_action.setCheckable(True)
        self._tile_select_action.setEnabled(False)
        self._tile_select_action.setShortcut(QKeySequence("T"))
        self._tile_select_action.toggled.connect(self._on_tile_select_toggled)
        edit_menu.addAction(self._tile_select_action)

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

        edit_menu.addSeparator()

        self._copy_tiles_action = QAction("Copy Tiles", self)
        self._copy_tiles_action.setShortcut(QKeySequence.StandardKey.Copy)
        self._copy_tiles_action.setEnabled(False)
        self._copy_tiles_action.triggered.connect(self._on_copy_tiles)
        self.addAction(self._copy_tiles_action)
        edit_menu.addAction(self._copy_tiles_action)

        self._cut_tiles_action = QAction("Cut Tiles", self)
        self._cut_tiles_action.setShortcut(QKeySequence.StandardKey.Cut)
        self._cut_tiles_action.setEnabled(False)
        self._cut_tiles_action.triggered.connect(self._on_cut_tiles)
        self.addAction(self._cut_tiles_action)
        edit_menu.addAction(self._cut_tiles_action)

        self._paste_tiles_action = QAction("Paste Tiles", self)
        self._paste_tiles_action.setShortcut(QKeySequence.StandardKey.Paste)
        self._paste_tiles_action.setEnabled(False)
        self._paste_tiles_action.triggered.connect(self._on_paste_tiles)
        self.addAction(self._paste_tiles_action)
        edit_menu.addAction(self._paste_tiles_action)

        self._delete_selected_entity_action = QAction(self)
        self._delete_selected_entity_action.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        self._delete_selected_entity_action.triggered.connect(self._on_delete_active_selection)
        self.addAction(self._delete_selected_entity_action)

        self._clear_selection_action = QAction(self)
        self._clear_selection_action.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        self._clear_selection_action.triggered.connect(self._on_clear_active_selection)
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

        self._entities_visibility_action = QAction("Show &Entities", self)
        self._entities_visibility_action.setCheckable(True)
        self._entities_visibility_action.setChecked(True)
        self._entities_visibility_action.toggled.connect(self._on_entities_visibility_toggled)
        view_menu.addAction(self._entities_visibility_action)

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

        self._add_tile_layer_action = QAction("Add Tile Layer...", self)
        self._add_tile_layer_action.setEnabled(False)
        self._add_tile_layer_action.triggered.connect(self._on_add_tile_layer_requested)
        area_menu.addAction(self._add_tile_layer_action)

        self._rename_tile_layer_action = QAction("Rename Current Layer...", self)
        self._rename_tile_layer_action.setEnabled(False)
        self._rename_tile_layer_action.triggered.connect(
            lambda: self._on_rename_tile_layer_requested(self._layer_panel.active_layer)
        )
        area_menu.addAction(self._rename_tile_layer_action)

        self._delete_tile_layer_action = QAction("Delete Current Layer...", self)
        self._delete_tile_layer_action.setEnabled(False)
        self._delete_tile_layer_action.triggered.connect(
            lambda: self._on_delete_tile_layer_requested(self._layer_panel.active_layer)
        )
        area_menu.addAction(self._delete_tile_layer_action)

        self._move_tile_layer_up_action = QAction("Move Current Layer Up", self)
        self._move_tile_layer_up_action.setEnabled(False)
        self._move_tile_layer_up_action.triggered.connect(
            lambda: self._on_move_tile_layer_requested(self._layer_panel.active_layer, -1)
        )
        area_menu.addAction(self._move_tile_layer_up_action)

        self._move_tile_layer_down_action = QAction("Move Current Layer Down", self)
        self._move_tile_layer_down_action.setEnabled(False)
        self._move_tile_layer_down_action.triggered.connect(
            lambda: self._on_move_tile_layer_requested(self._layer_panel.active_layer, 1)
        )
        area_menu.addAction(self._move_tile_layer_down_action)

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
        if not start_dir and self._manifest is not None:
            start_dir = str(self._manifest.project_root)

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
        self._area_panel.set_areas(
            discover_areas(self._manifest),
            list(self._manifest.area_paths),
        )

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
            widget = ItemEditorWidget(
                content_id,
                file_path,
                browse_asset_callback=self._browse_project_asset,
            )
        if widget is None and content_type == ContentType.PROJECT_MANIFEST:
            area_ids: list[str] = []
            if self._manifest is not None:
                area_ids = [entry.area_id for entry in discover_areas(self._manifest)]
            widget = ProjectManifestEditorWidget(file_path, area_ids=area_ids)
        if widget is None and content_type == ContentType.SHARED_VARIABLES:
            widget = SharedVariablesEditorWidget(file_path)
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
                    ProjectManifestEditorWidget,
                    SharedVariablesEditorWidget,
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
            self._status_area.setText(content_id)
            self._save_action.setEnabled(True)
            self._cell_flags_action.setEnabled(True)
            self._set_area_actions_enabled(True)

            # Populate tileset browser for this area
            if self._catalog is not None:
                canvas = self._active_canvas()
                current_index = canvas.tileset_index_hint if canvas is not None else 0
                selected_gid = canvas.selected_gid if canvas is not None else 0
                selected_block = canvas.selected_gid_block if canvas is not None else None
                erase_mode = canvas.brush_erase_mode if canvas is not None else True
                self._tileset_panel.set_tilesets(
                    doc.tilesets,
                    self._catalog,
                    current_index=current_index,
                    selected_gid=selected_gid,
                    selected_block=selected_block,
                    erase_mode=erase_mode,
                )

            # Reconnect layer visibility signals to the active canvas
            canvas = self._active_canvas()
            if canvas is not None:
                self._layer_panel.set_active_layer(canvas.active_layer)
                self._connect_canvas(canvas)
                can_paint = bool(doc.tile_layers)
                self._paint_tiles_action.setEnabled(bool(doc.tile_layers and doc.tilesets))
                self._select_action.setEnabled(True)
                self._tile_select_action.setEnabled(can_paint)
                self._set_cell_flags_action_state(canvas.cell_flags_edit_mode)
                self._set_paint_tiles_action_state(canvas.tile_paint_mode)
                self._set_select_action_state(canvas.select_mode)
                self._set_tile_select_action_state(canvas.tile_select_mode)
                self._entities_visibility_action.blockSignals(True)
                self._entities_visibility_action.setChecked(self._entities_visible)
                self._entities_visibility_action.blockSignals(False)
                self._apply_active_brush_to_canvas(canvas)
                self._status_zoom.setText(f"{canvas.zoom_level:.0%}")
                self._refresh_render_properties_target()
                self._refresh_entity_instance_panel()
                self._sync_json_edit_actions()
                self._refresh_layer_action_state()
                self._refresh_tile_selection_actions()
                if can_paint or canvas.select_mode or canvas.tile_select_mode:
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
            self._tile_select_action.setEnabled(False)
            self._set_area_actions_enabled(False)
            self._set_cell_flags_action_state(False)
            self._set_paint_tiles_action_state(False)
            self._set_select_action_state(False)
            self._set_tile_select_action_state(False)
            self._render_target_kind = None
            self._render_target_ref = None
            self._render_panel.clear_target()
            self._active_instance_entity_id = None
            self._entity_instance_panel.clear_entity()
            self._sync_json_edit_actions()
            self._refresh_layer_action_state()
            self._refresh_tile_selection_actions()
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
            self._tile_select_action.setEnabled(False)
            self._set_area_actions_enabled(False)
            self._set_cell_flags_action_state(False)
            self._set_paint_tiles_action_state(False)
            self._set_select_action_state(False)
            self._set_tile_select_action_state(False)
            self._render_target_kind = None
            self._render_target_ref = None
            self._render_panel.clear_target()
            self._active_instance_entity_id = None
            self._entity_instance_panel.clear_entity()
            self._sync_json_edit_actions()
            self._refresh_layer_action_state()
            self._refresh_tile_selection_actions()

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
            self._add_tile_layer_action,
        ):
            action.setEnabled(enabled)
        if not enabled:
            self._rename_tile_layer_action.setEnabled(False)
            self._delete_tile_layer_action.setEnabled(False)
            self._move_tile_layer_up_action.setEnabled(False)
            self._move_tile_layer_down_action.setEnabled(False)

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

    def _populate_area_context_menu(self, menu, content_id: str, file_path: Path) -> None:
        self._add_duplicate_area_action(menu, content_id, file_path)
        self._add_rename_content_action(menu, ContentType.AREA, content_id, file_path)
        self._add_delete_content_action(menu, ContentType.AREA, content_id, file_path)

    def _add_duplicate_area_action(self, menu, content_id: str, file_path: Path) -> None:
        menu.addSeparator()
        duplicate_action = QAction("Duplicate Area...", self)
        duplicate_action.triggered.connect(
            lambda: self._on_duplicate_area(content_id, file_path)
        )
        menu.addAction(duplicate_action)

    def _populate_template_context_menu(self, menu, content_id: str, file_path: Path) -> None:
        self._add_rename_content_action(
            menu,
            ContentType.ENTITY_TEMPLATE,
            content_id,
            file_path,
        )
        self._add_delete_content_action(
            menu,
            ContentType.ENTITY_TEMPLATE,
            content_id,
            file_path,
        )

    def _populate_item_context_menu(self, menu, content_id: str, file_path: Path) -> None:
        self._add_rename_content_action(menu, ContentType.ITEM, content_id, file_path)
        self._add_delete_content_action(menu, ContentType.ITEM, content_id, file_path)

    def _populate_global_entity_context_menu(self, menu, entity_id: str) -> None:
        menu.addSeparator()
        rename_action = QAction("Rename ID...", self)
        rename_action.triggered.connect(
            lambda: self._on_rename_global_entity_id(entity_id)
        )
        menu.addAction(rename_action)
        delete_action = QAction("Delete Global Entity...", self)
        delete_action.triggered.connect(
            lambda: self._on_delete_global_entity(entity_id)
        )
        menu.addAction(delete_action)

    def _populate_folder_context_menu(
        self,
        menu,
        content_type: ContentType,
        relative_path: str,
        folder_path: Path,
        root_dir: Path,
    ) -> None:
        menu.addSeparator()
        new_folder_action = QAction("New Folder...", self)
        new_folder_action.triggered.connect(
            lambda: self._on_new_content_folder(
                root_dir=root_dir,
                parent_relative_path=relative_path,
            )
        )
        menu.addAction(new_folder_action)

        rename_action = QAction("Rename/Move Folder...", self)
        rename_action.triggered.connect(
            lambda: self._on_rename_content_folder(
                content_type=content_type,
                root_dir=root_dir,
                relative_path=relative_path,
                folder_path=folder_path,
            )
        )
        menu.addAction(rename_action)

        delete_action = QAction("Delete Folder...", self)
        delete_action.setEnabled(folder_path.is_dir() and not any(folder_path.iterdir()))
        delete_action.triggered.connect(
            lambda: self._on_delete_empty_content_folder(
                folder_path=folder_path,
                relative_path=relative_path,
            )
        )
        menu.addAction(delete_action)

    def _populate_empty_space_context_menu(
        self,
        menu,
        _content_type: ContentType,
        root_dirs: list[Path],
        current_relative_path: str | None,
        _current_folder_path: Path | None,
        current_root_dir: Path | None,
    ) -> None:
        root_dir = current_root_dir or (root_dirs[0] if root_dirs else None)
        if root_dir is None:
            return
        menu.addSeparator()
        new_folder_action = QAction("New Folder...", self)
        new_folder_action.triggered.connect(
            lambda: self._on_new_content_folder(
                root_dir=root_dir,
                parent_relative_path=current_relative_path,
            )
        )
        menu.addAction(new_folder_action)

    def _populate_dialogue_context_menu(
        self,
        menu,
        content_id: str,
        file_path: Path,
    ) -> None:
        self._add_rename_content_action(menu, ContentType.DIALOGUE, content_id, file_path)
        self._add_delete_content_action(menu, ContentType.DIALOGUE, content_id, file_path)

    def _populate_command_context_menu(
        self,
        menu,
        content_id: str,
        file_path: Path,
    ) -> None:
        self._add_rename_content_action(
            menu,
            ContentType.NAMED_COMMAND,
            content_id,
            file_path,
        )
        self._add_delete_content_action(
            menu,
            ContentType.NAMED_COMMAND,
            content_id,
            file_path,
        )

    def _add_rename_content_action(
        self,
        menu,
        content_type: ContentType,
        content_id: str,
        file_path: Path,
    ) -> None:
        menu.addSeparator()
        rename_action = QAction("Rename/Move...", self)
        rename_action.triggered.connect(
            lambda: self._on_rename_project_content(
                content_type,
                content_id,
                file_path,
            )
        )
        menu.addAction(rename_action)

    def _add_delete_content_action(
        self,
        menu,
        content_type: ContentType,
        content_id: str,
        file_path: Path,
    ) -> None:
        delete_action = QAction("Delete...", self)
        delete_action.triggered.connect(
            lambda: self._on_delete_project_content(
                content_type,
                content_id,
                file_path,
            )
        )
        menu.addAction(delete_action)

    def _on_rename_project_content(
        self,
        content_type: ContentType,
        content_id: str,
        file_path: Path,
    ) -> None:
        if self._manifest is None:
            return
        if not self._maybe_save_dirty_tabs():
            return
        rename_config = self._rename_config_for_content(content_type)
        if rename_config is None:
            return
        prefix, roots, reference_matcher, title = rename_config
        relative_name = self._relative_content_name(content_id, prefix)
        if relative_name is None:
            QMessageBox.warning(
                self,
                "Rename Unsupported",
                f"Cannot rename '{content_id}' through this workflow.",
            )
            return

        new_relative_name = self._prompt_content_relative_name(
            title=title,
            current_relative_name=relative_name,
        )
        if new_relative_name is None:
            return
        if new_relative_name == relative_name:
            return

        root_dir = self._root_dir_for_content_file(file_path, roots)
        if root_dir is None:
            QMessageBox.warning(
                self,
                "Rename Unsupported",
                f"Could not determine the content root for '{file_path.name}'.",
            )
            return

        candidate_path = root_dir / new_relative_name
        if content_type == ContentType.ASSET or candidate_path.suffix != file_path.suffix:
            candidate_path = candidate_path.with_suffix(file_path.suffix)
        new_file_path = candidate_path
        new_file_path = new_file_path.resolve()
        try:
            new_file_path.relative_to(root_dir.resolve())
        except ValueError:
            QMessageBox.warning(
                self,
                "Invalid Destination",
                "Renamed content must stay inside its configured project root.",
            )
            return
        if new_file_path == file_path.resolve():
            return
        if new_file_path.exists():
            QMessageBox.warning(
                self,
                "Destination Exists",
                f"'{new_file_path}' already exists.",
            )
            return

        if content_type == ContentType.ASSET:
            normalized_relative_name = (
                str(new_file_path.relative_to(root_dir.resolve()))
                .replace("\\", "/")
                .strip("/")
            )
        else:
            normalized_relative_name = new_relative_name.replace("\\", "/").strip("/")
        new_content_id = (
            f"{prefix}/{normalized_relative_name}" if prefix else normalized_relative_name
        )
        old_reference_value = content_id
        new_reference_value = new_content_id
        if content_type == ContentType.ASSET:
            old_reference_value = self._authored_asset_path_for(file_path) or content_id
            new_reference_value = (
                self._authored_asset_path_for(new_file_path) or new_content_id
            )
        try:
            reference_updates = self._collect_reference_updates(
                old_value=old_reference_value,
                new_value=new_reference_value,
                matcher=reference_matcher,
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Rename Failed",
                f"Could not build the reference update preview:\n{exc}",
            )
            return

        if not self._confirm_content_rename_preview(
            title=title,
            old_content_id=content_id,
            new_content_id=new_content_id,
            old_file_path=file_path,
            new_file_path=new_file_path,
            reference_updates=reference_updates,
        ):
            return

        was_open = self._tab_widget.content_info(content_id) is not None
        try:
            for update in reference_updates:
                update.file_path.write_text(update.updated_text, encoding="utf-8")
            new_file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.rename(new_file_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Rename Failed",
                f"Could not rename '{content_id}':\n{exc}",
            )
            return

        self._tab_widget.close_all()
        self._area_docs.clear()
        self._json_dirty_bound.clear()
        self._refresh_project_metadata_surfaces()
        self._refresh_area_panel()

        if content_type == ContentType.AREA:
            self._area_panel.highlight_area(new_content_id)
            if was_open:
                self._open_area(new_content_id, new_file_path)
        else:
            target_panel = self._panel_for_content_type(content_type)
            if target_panel is not None:
                target_panel.select_by_id(new_content_id)
            if was_open:
                self._open_content(new_content_id, new_file_path, content_type)

        self.statusBar().showMessage(
            f"Renamed {content_id} to {new_content_id}.",
            3500,
        )

    def _on_duplicate_area(self, content_id: str, file_path: Path) -> None:
        if self._manifest is None:
            return
        if not self._maybe_save_dirty_tabs():
            return
        relative_name = self._relative_content_name(content_id, AREA_ID_PREFIX)
        if relative_name is None:
            QMessageBox.warning(
                self,
                "Duplicate Area",
                f"Cannot duplicate '{content_id}' through this workflow.",
            )
            return
        new_relative_name = self._prompt_content_relative_name(
            title="Duplicate Area",
            current_relative_name=self._suggest_duplicate_area_relative_name(relative_name),
        )
        if new_relative_name is None:
            return
        duplicate_mode = self._prompt_area_duplicate_mode()
        if duplicate_mode is None:
            return
        try:
            new_content_id, new_file_path = self._duplicate_area_file(
                source_content_id=content_id,
                source_file_path=file_path,
                new_relative_name=new_relative_name,
                duplicate_mode=duplicate_mode,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Duplicate Area", str(exc))
            return
        self._refresh_area_panel()
        self._open_area(new_content_id, new_file_path)
        self._area_panel.highlight_area(new_content_id)
        self.statusBar().showMessage(f"Duplicated area to {new_content_id}.", 3000)

    def _duplicate_area_file(
        self,
        *,
        source_content_id: str,
        source_file_path: Path,
        new_relative_name: str,
        duplicate_mode: str,
    ) -> tuple[str, Path]:
        if self._manifest is None:
            raise ValueError("Open a project before duplicating an area.")
        normalized_relative_name = new_relative_name.strip().replace("\\", "/").strip("/")
        if not normalized_relative_name:
            raise ValueError("Area ID must not be empty.")
        if normalized_relative_name.endswith(".json"):
            normalized_relative_name = normalized_relative_name[:-5]
        if not normalized_relative_name:
            raise ValueError("Area ID must not be empty.")

        area_roots = list(self._manifest.area_paths)
        root_dir = self._root_dir_for_content_file(source_file_path, area_roots)
        if root_dir is None:
            root_dir = self._default_area_root()
        new_file_path = (root_dir / Path(normalized_relative_name)).with_suffix(".json").resolve()
        try:
            new_file_path.relative_to(root_dir.resolve())
        except ValueError as exc:
            raise ValueError("Duplicated areas must stay inside their configured project root.") from exc
        new_content_id = f"{AREA_ID_PREFIX}/{normalized_relative_name}"
        if new_file_path.exists():
            raise ValueError(f"An area already exists at {new_content_id}.")

        source_document = self._area_docs.get(source_content_id)
        if source_document is None:
            source_document = load_area_document(source_file_path)
        duplicated = self._build_duplicated_area_document(
            source_document,
            duplicate_mode=duplicate_mode,
        )
        new_file_path.parent.mkdir(parents=True, exist_ok=True)
        save_area_document(new_file_path, duplicated)
        return new_content_id, new_file_path

    def _build_duplicated_area_document(
        self,
        source_document: AreaDocument,
        *,
        duplicate_mode: str,
    ) -> AreaDocument:
        if duplicate_mode == _AREA_DUPLICATE_LAYOUT:
            layout_data: dict[str, object] = {
                "tile_size": source_document.tile_size,
                "tilesets": [copy.deepcopy(tileset.to_dict()) for tileset in source_document.tilesets],
                "tile_layers": [copy.deepcopy(layer.to_dict()) for layer in source_document.tile_layers],
            }
            if source_document.cell_flags:
                layout_data["cell_flags"] = copy.deepcopy(source_document.cell_flags)
            return AreaDocument.from_dict(layout_data)

        duplicated_data = copy.deepcopy(source_document.to_dict())
        raw_entities = duplicated_data.get("entities", [])
        if not isinstance(raw_entities, list):
            raise ValueError("Area JSON must keep entities as an array.")
        used_ids = self._project_used_entity_ids()
        id_remap: dict[str, str] = {}
        for raw_entity in raw_entities:
            if not isinstance(raw_entity, dict):
                continue
            old_entity_id = str(raw_entity.get("id", "")).strip()
            if not old_entity_id:
                continue
            new_entity_id = self._generate_duplicate_entity_id(
                old_entity_id,
                used_ids=used_ids,
            )
            raw_entity["id"] = new_entity_id
            id_remap[old_entity_id] = new_entity_id
            used_ids.add(new_entity_id)
        matcher = self._area_entity_reference_matcher()
        updated_data = duplicated_data
        for old_entity_id, new_entity_id in id_remap.items():
            updated_data, _changed_paths = self._replace_reference_keys_in_json_value(
                updated_data,
                old_value=old_entity_id,
                new_value=new_entity_id,
                matcher=matcher,
            )
        return AreaDocument.from_dict(updated_data)

    @staticmethod
    def _suggest_duplicate_area_relative_name(relative_name: str) -> str:
        normalized = relative_name.strip().replace("\\", "/").strip("/")
        if not normalized:
            return "copy"
        return f"{normalized}_copy"

    def _prompt_area_duplicate_mode(self) -> str | None:
        selected, accepted = QInputDialog.getItem(
            self,
            "Duplicate Area",
            "Duplicate mode",
            [_AREA_DUPLICATE_FULL, _AREA_DUPLICATE_LAYOUT],
            0,
            False,
        )
        if not accepted:
            return None
        normalized = str(selected).strip()
        if normalized not in {_AREA_DUPLICATE_FULL, _AREA_DUPLICATE_LAYOUT}:
            return None
        return normalized

    @staticmethod
    def _generate_duplicate_entity_id(base_entity_id: str, *, used_ids: set[str]) -> str:
        normalized_base = base_entity_id.strip().replace(" ", "_")
        if not normalized_base:
            normalized_base = "entity"
        highest = 0
        base_taken = False
        prefix = f"{normalized_base}_"
        for used_id in used_ids:
            if used_id == normalized_base:
                base_taken = True
                continue
            if not used_id.startswith(prefix):
                continue
            suffix = used_id[len(prefix) :]
            if suffix.isdigit():
                highest = max(highest, int(suffix))
        if not base_taken and highest == 0:
            return normalized_base
        return f"{normalized_base}_{highest + 1}"

    def _on_delete_project_content(
        self,
        content_type: ContentType,
        content_id: str,
        file_path: Path,
    ) -> None:
        if self._manifest is None:
            return
        if not self._maybe_save_dirty_tabs():
            return
        rename_config = self._rename_config_for_content(content_type)
        if rename_config is None:
            return
        _prefix, _roots, matcher, title = rename_config
        reference_value = content_id
        if content_type == ContentType.ASSET:
            reference_value = self._authored_asset_path_for(file_path) or content_id
        try:
            reference_usages = self._collect_reference_usages(
                value=reference_value,
                matcher=matcher,
                skip_files={file_path.resolve()},
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Delete Failed",
                f"Could not build the usage preview:\n{exc}",
            )
            return

        if not self._confirm_content_delete_preview(
            title=title.replace("Rename/Move", "Delete"),
            content_id=content_id,
            file_path=file_path,
            reference_usages=reference_usages,
        ):
            return

        try:
            file_path.unlink()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Delete Failed",
                f"Could not delete '{content_id}':\n{exc}",
            )
            return

        self._tab_widget.close_content(content_id)
        self._area_docs.pop(content_id, None)
        self._json_dirty_bound.discard(content_id)
        self._refresh_project_metadata_surfaces()
        self._refresh_area_panel()
        self.statusBar().showMessage(f"Deleted {content_id}.", 3500)

    def _on_rename_global_entity_id(self, entity_id: str) -> None:
        if self._manifest is None:
            return
        if not self._maybe_save_dirty_tabs():
            return
        new_entity_id, accepted = QInputDialog.getText(
            self,
            "Rename Global Entity ID",
            "New entity id",
            text=entity_id,
        )
        if not accepted:
            return
        normalized = new_entity_id.strip()
        if not normalized:
            QMessageBox.warning(
                self,
                "Invalid Entity ID",
                "The new entity id must not be blank.",
            )
            return
        if normalized == entity_id:
            return
        self._apply_global_entity_id_rename(entity_id, normalized)

    def _apply_global_entity_id_rename(
        self,
        entity_id: str,
        normalized: str,
    ) -> None:
        if self._manifest is None:
            return
        for usage in self._project_entity_id_usages():
            if usage.entity_id != normalized:
                continue
            QMessageBox.warning(
                self,
                "Duplicate Entity ID",
                f"Entity id '{normalized}' is already used by "
                f"{self._describe_entity_id_usage(usage)}.",
            )
            return

        project_file = self._manifest.project_file.resolve()
        try:
            project_data = json.loads(project_file.read_text(encoding="utf-8"))
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Rename Failed",
                f"Could not read project.json:\n{exc}",
            )
            return
        raw_entities = project_data.get("global_entities", [])
        if not isinstance(raw_entities, list):
            QMessageBox.warning(
                self,
                "Rename Failed",
                "project.json global_entities must be a JSON array.",
            )
            return

        target_index: int | None = None
        for index, raw_entity in enumerate(raw_entities):
            if not isinstance(raw_entity, dict):
                continue
            if str(raw_entity.get("id", "")).strip() != entity_id:
                continue
            updated_entity = dict(raw_entity)
            updated_entity["id"] = normalized
            raw_entities[index] = updated_entity
            target_index = index
            break
        if target_index is None:
            QMessageBox.warning(
                self,
                "Rename Failed",
                f"Could not find global entity '{entity_id}' in project.json.",
            )
            return

        matcher = self._area_entity_reference_matcher()
        updated_project_data, project_changed_paths = self._replace_reference_keys_in_json_value(
            project_data,
            old_value=entity_id,
            new_value=normalized,
            matcher=matcher,
        )
        project_update = _JsonReferenceFileUpdate(
            file_path=project_file,
            updated_text=f"{format_json_for_editor(updated_project_data)}\n",
            changed_paths=tuple((f"$.global_entities[{target_index}].id", *project_changed_paths)),
        )
        try:
            other_updates = self._collect_reference_updates(
                old_value=entity_id,
                new_value=normalized,
                matcher=matcher,
                skip_files={project_file},
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Rename Failed",
                f"Could not build the reference update preview:\n{exc}",
            )
            return
        reference_updates = [project_update, *other_updates]

        if not self._confirm_global_entity_rename_preview(
            old_entity_id=entity_id,
            new_entity_id=normalized,
            reference_updates=reference_updates,
        ):
            return

        was_open = self._tab_widget.content_info("project/global_entities") is not None
        try:
            for update in reference_updates:
                update.file_path.write_text(update.updated_text, encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Rename Failed",
                f"Could not rename global entity '{entity_id}':\n{exc}",
            )
            return

        self._refresh_project_metadata_surfaces()
        if was_open:
            self._open_global_entities_tab(normalized)
        else:
            self._global_entities_panel.select_entity(normalized)
        self.statusBar().showMessage(
            f"Renamed global entity {entity_id} to {normalized}.",
            3500,
        )

    def _on_delete_global_entity(self, entity_id: str) -> None:
        if self._manifest is None:
            return
        if not self._maybe_save_dirty_tabs():
            return

        project_file = self._manifest.project_file.resolve()
        try:
            reference_usages = self._collect_reference_usages(
                value=entity_id,
                matcher=self._area_entity_reference_matcher(),
                skip_files=set(),
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Delete Failed",
                f"Could not build the usage preview:\n{exc}",
            )
            return

        if not self._confirm_global_entity_delete_preview(
            entity_id=entity_id,
            reference_usages=reference_usages,
        ):
            return

        try:
            project_data = json.loads(project_file.read_text(encoding="utf-8"))
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Delete Failed",
                f"Could not read project.json:\n{exc}",
            )
            return
        raw_entities = project_data.get("global_entities", [])
        if not isinstance(raw_entities, list):
            QMessageBox.warning(
                self,
                "Delete Failed",
                "project.json global_entities must be a JSON array.",
            )
            return

        updated_entities = [
            raw_entity
            for raw_entity in raw_entities
            if not (
                isinstance(raw_entity, dict)
                and str(raw_entity.get("id", "")).strip() == entity_id
            )
        ]
        if len(updated_entities) == len(raw_entities):
            QMessageBox.warning(
                self,
                "Delete Failed",
                f"Could not find global entity '{entity_id}' in project.json.",
            )
            return
        project_data["global_entities"] = updated_entities
        try:
            project_file.write_text(
                f"{format_json_for_editor(project_data)}\n",
                encoding="utf-8",
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Delete Failed",
                f"Could not update project.json:\n{exc}",
            )
            return

        self._refresh_project_metadata_surfaces()
        if self._tab_widget.content_info("project/global_entities") is not None:
            self._open_global_entities_tab(None)
        self.statusBar().showMessage(f"Deleted global entity {entity_id}.", 3500)

    def _on_tab_close_requested(self, content_id: str, _content_type: object) -> None:
        if not self._maybe_save_dirty_tabs([content_id]):
            return
        self._tab_widget.close_content(content_id)

    def _on_tab_closed(self, content_id: str) -> None:
        self._area_docs.pop(content_id, None)
        self._json_dirty_bound.discard(content_id)

    def _rename_config_for_content(
        self,
        content_type: ContentType,
    ) -> tuple[str, list[Path], _ReferenceKeyMatcher, str] | None:
        if self._manifest is None:
            return None
        if content_type == ContentType.AREA:
            return (
                AREA_ID_PREFIX,
                list(self._manifest.area_paths),
                _ReferenceKeyMatcher(
                    exact_keys=frozenset(
                        {
                            "startup_area",
                            "area_id",
                            "destination_area_id",
                            "source_area_id",
                        }
                    ),
                    suffix_keys=frozenset({"_area_id"}),
                ),
                "Rename/Move Area",
            )
        if content_type == ContentType.ENTITY_TEMPLATE:
            return (
                "entity_templates",
                list(self._manifest.entity_template_paths),
                _ReferenceKeyMatcher(
                    exact_keys=frozenset({"template", "template_id"}),
                ),
                "Rename/Move Template",
            )
        if content_type == ContentType.ITEM:
            return (
                "items",
                list(self._manifest.item_paths),
                _ReferenceKeyMatcher(
                    exact_keys=frozenset({"item_id"}),
                    suffix_keys=frozenset({"_item_id"}),
                ),
                "Rename/Move Item",
            )
        if content_type == ContentType.DIALOGUE:
            return (
                _DIALOGUE_ID_PREFIX,
                list(self._manifest.dialogue_paths),
                _ReferenceKeyMatcher(
                    exact_keys=frozenset({"dialogue_path"}),
                    suffix_keys=frozenset({"_dialogue_path"}),
                ),
                "Rename/Move Dialogue",
            )
        if content_type == ContentType.NAMED_COMMAND:
            return (
                _COMMAND_ID_PREFIX,
                list(self._manifest.command_paths),
                _ReferenceKeyMatcher(
                    exact_keys=frozenset({"command_id"}),
                ),
                "Rename/Move Command",
            )
        if content_type == ContentType.ASSET:
            return (
                "",
                list(self._manifest.asset_paths),
                _ReferenceKeyMatcher(
                    exact_keys=frozenset({"path", "atlas"}),
                    suffix_keys=frozenset({"_path"}),
                ),
                "Rename/Move Asset",
            )
        return None

    @staticmethod
    def _relative_content_name(content_id: str, prefix: str | None) -> str | None:
        normalized = content_id.replace("\\", "/")
        stripped_prefix = (prefix or "").strip("/")
        if stripped_prefix:
            expected_prefix = f"{stripped_prefix}/"
            if not normalized.startswith(expected_prefix):
                return None
            relative_name = normalized[len(expected_prefix) :].strip("/")
        else:
            relative_name = normalized.strip("/")
        return relative_name or None

    def _prompt_content_relative_name(
        self,
        *,
        title: str,
        current_relative_name: str,
    ) -> str | None:
        new_value, accepted = QInputDialog.getText(
            self,
            title,
            "New relative id/path",
            text=current_relative_name,
        )
        if not accepted:
            return None
        normalized = new_value.strip().replace("\\", "/").strip("/")
        if not normalized:
            QMessageBox.warning(
                self,
                "Invalid Name",
                "The new relative id/path must not be blank.",
            )
            return None
        return normalized

    def _prompt_folder_relative_path(
        self,
        *,
        title: str,
        current_relative_path: str,
    ) -> str | None:
        new_value, accepted = QInputDialog.getText(
            self,
            title,
            "Folder relative path",
            text=current_relative_path,
        )
        if not accepted:
            return None
        normalized = new_value.strip().replace("\\", "/").strip("/")
        if not normalized:
            QMessageBox.warning(
                self,
                "Invalid Folder",
                "The folder path must not be blank.",
            )
            return None
        return normalized

    def _on_new_content_folder(
        self,
        *,
        root_dir: Path,
        parent_relative_path: str | None,
    ) -> None:
        initial_value = f"{parent_relative_path}/" if parent_relative_path else ""
        relative_path = self._prompt_folder_relative_path(
            title="New Folder",
            current_relative_path=initial_value,
        )
        if relative_path is None:
            return
        self._apply_new_content_folder(root_dir=root_dir, relative_path=relative_path)

    def _apply_new_content_folder(self, *, root_dir: Path, relative_path: str) -> None:
        folder_path = (root_dir / relative_path).resolve()
        try:
            folder_path.relative_to(root_dir.resolve())
        except ValueError:
            QMessageBox.warning(
                self,
                "Invalid Folder",
                "Folders must stay inside their configured project root.",
            )
            return
        if folder_path.exists():
            QMessageBox.warning(
                self,
                "Folder Exists",
                f"'{folder_path}' already exists.",
            )
            return
        folder_path.mkdir(parents=True, exist_ok=False)
        self._refresh_project_metadata_surfaces()
        self._refresh_area_panel()
        self.statusBar().showMessage(f"Created folder {relative_path}.", 2500)

    def _on_delete_empty_content_folder(
        self,
        *,
        folder_path: Path,
        relative_path: str,
    ) -> None:
        if not folder_path.is_dir():
            return
        if any(folder_path.iterdir()):
            QMessageBox.information(
                self,
                "Folder Not Empty",
                "Only completely empty folders can be deleted.",
            )
            return
        folder_path.rmdir()
        self._refresh_project_metadata_surfaces()
        self._refresh_area_panel()
        self.statusBar().showMessage(f"Deleted folder {relative_path}.", 2500)

    def _on_rename_content_folder(
        self,
        *,
        content_type: ContentType,
        root_dir: Path,
        relative_path: str,
        folder_path: Path,
    ) -> None:
        if self._manifest is None:
            return
        if not self._maybe_save_dirty_tabs():
            return
        new_relative_path = self._prompt_folder_relative_path(
            title="Rename/Move Folder",
            current_relative_path=relative_path,
        )
        if new_relative_path is None or new_relative_path == relative_path:
            return
        self._apply_content_folder_move(
            content_type=content_type,
            root_dir=root_dir,
            relative_path=relative_path,
            folder_path=folder_path,
            new_relative_path=new_relative_path,
        )

    def _apply_content_folder_move(
        self,
        *,
        content_type: ContentType,
        root_dir: Path,
        relative_path: str,
        folder_path: Path,
        new_relative_path: str,
    ) -> None:
        rename_config = self._rename_config_for_content(content_type)
        if rename_config is None:
            return
        _prefix, _roots, matcher, title = rename_config
        new_folder_path = (root_dir / new_relative_path).resolve()
        try:
            new_folder_path.relative_to(root_dir.resolve())
        except ValueError:
            QMessageBox.warning(
                self,
                "Invalid Destination",
                "Moved folders must stay inside their configured project root.",
            )
            return
        if new_folder_path == folder_path.resolve():
            return
        if new_folder_path.exists():
            QMessageBox.warning(
                self,
                "Destination Exists",
                f"'{new_folder_path}' already exists.",
            )
            return
        moved_files = self._folder_files_for_content_type(content_type, folder_path)
        replacements: list[tuple[str, str]] = []
        for file_path in moved_files:
            old_value = self._reference_value_for_content_file(content_type, file_path, root_dir)
            if old_value is None:
                continue
            relative_child = file_path.resolve().relative_to(folder_path.resolve())
            target_file_path = new_folder_path / relative_child
            new_value = self._reference_value_for_content_file(
                content_type,
                target_file_path,
                root_dir,
            )
            if new_value is None or new_value == old_value:
                continue
            replacements.append((old_value, new_value))
        try:
            reference_updates = self._collect_reference_updates_for_replacements(
                replacements=replacements,
                matcher=matcher,
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Folder Move Failed",
                f"Could not build the reference update preview:\n{exc}",
            )
            return
        if not self._confirm_folder_move_preview(
            title=title,
            old_relative_path=relative_path,
            new_relative_path=new_relative_path,
            moved_files=moved_files,
            reference_updates=reference_updates,
        ):
            return
        try:
            for update in reference_updates:
                update.file_path.write_text(update.updated_text, encoding="utf-8")
            new_folder_path.parent.mkdir(parents=True, exist_ok=True)
            folder_path.rename(new_folder_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Folder Move Failed",
                f"Could not move folder '{relative_path}':\n{exc}",
            )
            return
        self._tab_widget.close_all()
        self._area_docs.clear()
        self._json_dirty_bound.clear()
        self._refresh_project_metadata_surfaces()
        self._refresh_area_panel()
        self.statusBar().showMessage(
            f"Moved folder {relative_path} to {new_relative_path}.",
            3500,
        )

    def _folder_files_for_content_type(
        self,
        content_type: ContentType,
        folder_path: Path,
    ) -> list[Path]:
        if content_type == ContentType.ASSET:
            return sorted(path for path in folder_path.rglob("*") if path.is_file())
        return sorted(folder_path.rglob("*.json"))

    def _reference_value_for_content_file(
        self,
        content_type: ContentType,
        file_path: Path,
        root_dir: Path,
    ) -> str | None:
        resolved = file_path.resolve()
        if content_type == ContentType.ASSET:
            return self._authored_asset_path_for(resolved)
        rename_config = self._rename_config_for_content(content_type)
        if rename_config is None:
            return None
        prefix, _roots, _matcher, _title = rename_config
        try:
            relative = resolved.relative_to(root_dir.resolve())
        except ValueError:
            return None
        relative_name = str(relative.with_suffix("")).replace("\\", "/").strip("/")
        return f"{prefix}/{relative_name}".strip("/") if prefix else relative_name

    @staticmethod
    def _root_dir_for_content_file(file_path: Path, roots: list[Path]) -> Path | None:
        resolved = file_path.resolve()
        for root_dir in roots:
            try:
                resolved.relative_to(root_dir.resolve())
                return root_dir.resolve()
            except ValueError:
                continue
        return None

    def _panel_for_content_type(self, content_type: ContentType) -> FileTreePanel | None:
        if content_type == ContentType.ENTITY_TEMPLATE:
            return self._template_panel
        if content_type == ContentType.ITEM:
            return self._item_panel
        if content_type == ContentType.DIALOGUE:
            return self._dialogue_panel
        if content_type == ContentType.NAMED_COMMAND:
            return self._command_panel
        if content_type == ContentType.ASSET:
            return self._asset_panel
        return None

    def _collect_reference_updates(
        self,
        *,
        old_value: str,
        new_value: str,
        matcher: _ReferenceKeyMatcher,
        skip_files: set[Path] | None = None,
    ) -> list[_JsonReferenceFileUpdate]:
        updates: list[_JsonReferenceFileUpdate] = []
        skipped = {path.resolve() for path in (skip_files or set())}
        for file_path in self._project_json_reference_scan_files():
            if file_path.resolve() in skipped:
                continue
            data = json.loads(file_path.read_text(encoding="utf-8"))
            updated, changed_paths = self._replace_reference_keys_in_json_value(
                data,
                old_value=old_value,
                new_value=new_value,
                matcher=matcher,
            )
            if not changed_paths:
                continue
            updates.append(
                _JsonReferenceFileUpdate(
                    file_path=file_path,
                    updated_text=f"{format_json_for_editor(updated)}\n",
                    changed_paths=tuple(changed_paths),
                )
            )
        return updates

    def _collect_reference_usages(
        self,
        *,
        value: str,
        matcher: _ReferenceKeyMatcher,
        skip_files: set[Path] | None = None,
    ) -> list[_JsonReferenceUsage]:
        usages: list[_JsonReferenceUsage] = []
        skipped = {path.resolve() for path in (skip_files or set())}
        for file_path in self._project_json_reference_scan_files():
            if file_path.resolve() in skipped:
                continue
            data = json.loads(file_path.read_text(encoding="utf-8"))
            matched_paths = self._find_reference_paths_in_json_value(
                data,
                target_value=value,
                matcher=matcher,
            )
            if not matched_paths:
                continue
            usages.append(
                _JsonReferenceUsage(
                    file_path=file_path,
                    matched_paths=tuple(matched_paths),
                )
            )
        return usages

    def _collect_reference_updates_for_replacements(
        self,
        *,
        replacements: list[tuple[str, str]],
        matcher: _ReferenceKeyMatcher,
        skip_files: set[Path] | None = None,
    ) -> list[_JsonReferenceFileUpdate]:
        if not replacements:
            return []
        updates: list[_JsonReferenceFileUpdate] = []
        skipped = {path.resolve() for path in (skip_files or set())}
        for file_path in self._project_json_reference_scan_files():
            if file_path.resolve() in skipped:
                continue
            data = json.loads(file_path.read_text(encoding="utf-8"))
            updated = data
            changed_paths: list[str] = []
            for old_value, new_value in replacements:
                updated, child_paths = self._replace_reference_keys_in_json_value(
                    updated,
                    old_value=old_value,
                    new_value=new_value,
                    matcher=matcher,
                )
                changed_paths.extend(child_paths)
            if not changed_paths:
                continue
            updates.append(
                _JsonReferenceFileUpdate(
                    file_path=file_path,
                    updated_text=f"{format_json_for_editor(updated)}\n",
                    changed_paths=tuple(changed_paths),
                )
            )
        return updates

    def _project_json_reference_scan_files(self) -> list[Path]:
        if self._manifest is None:
            return []
        files: list[Path] = [self._manifest.project_file]
        if (
            self._manifest.shared_variables_path is not None
            and self._manifest.shared_variables_path.is_file()
        ):
            files.append(self._manifest.shared_variables_path.resolve())
        files.extend(entry.file_path.resolve() for entry in discover_areas(self._manifest))
        files.extend(
            entry.file_path.resolve()
            for entry in discover_entity_templates(self._manifest)
        )
        for path_list in (
            self._manifest.item_paths,
            self._manifest.command_paths,
            self._manifest.dialogue_paths,
        ):
            for root_dir in path_list:
                if not root_dir.is_dir():
                    continue
                files.extend(path.resolve() for path in sorted(root_dir.rglob("*.json")))
        for root_dir in self._manifest.asset_paths:
            if not root_dir.is_dir():
                continue
            files.extend(path.resolve() for path in sorted(root_dir.rglob("*.json")))
        unique: list[Path] = []
        seen: set[Path] = set()
        for file_path in files:
            resolved = file_path.resolve()
            if resolved in seen or not resolved.is_file():
                continue
            seen.add(resolved)
            unique.append(resolved)
        return unique

    def _replace_reference_keys_in_json_value(
        self,
        value: Any,
        *,
        old_value: str,
        new_value: str,
        matcher: _ReferenceKeyMatcher,
        path: str = "$",
    ) -> tuple[Any, list[str]]:
        changed_paths: list[str] = []
        if isinstance(value, dict):
            updated: dict[str, Any] = {}
            for key, child in value.items():
                child_path = f"{path}.{key}"
                if matcher.matches(key):
                    replaced_child, replaced_paths = self._replace_matched_reference_child(
                        child,
                        old_value=old_value,
                        new_value=new_value,
                        path=child_path,
                    )
                    if replaced_paths:
                        updated[key] = replaced_child
                        changed_paths.extend(replaced_paths)
                        continue
                updated_child, child_changes = self._replace_reference_keys_in_json_value(
                    child,
                    old_value=old_value,
                    new_value=new_value,
                    matcher=matcher,
                    path=child_path,
                )
                updated[key] = updated_child
                changed_paths.extend(child_changes)
            return updated, changed_paths
        if isinstance(value, list):
            updated_list: list[Any] = []
            for index, child in enumerate(value):
                updated_child, child_changes = self._replace_reference_keys_in_json_value(
                    child,
                    old_value=old_value,
                    new_value=new_value,
                    matcher=matcher,
                    path=f"{path}[{index}]",
                )
                updated_list.append(updated_child)
                changed_paths.extend(child_changes)
            return updated_list, changed_paths
        return value, changed_paths

    def _replace_matched_reference_child(
        self,
        child: Any,
        *,
        old_value: str,
        new_value: str,
        path: str,
    ) -> tuple[Any, list[str]]:
        if isinstance(child, str):
            if child == old_value:
                return new_value, [path]
            return child, []
        if isinstance(child, list):
            changed_paths: list[str] = []
            updated_list: list[Any] = []
            for index, item in enumerate(child):
                if isinstance(item, str) and item == old_value:
                    updated_list.append(new_value)
                    changed_paths.append(f"{path}[{index}]")
                else:
                    updated_list.append(item)
            return updated_list, changed_paths
        if isinstance(child, dict):
            changed_paths: list[str] = []
            updated_dict: dict[str, Any] = {}
            for dict_key, dict_value in child.items():
                if isinstance(dict_value, str) and dict_value == old_value:
                    updated_dict[dict_key] = new_value
                    changed_paths.append(f"{path}.{dict_key}")
                else:
                    updated_dict[dict_key] = dict_value
            return updated_dict, changed_paths
        return child, []

    def _find_reference_paths_in_json_value(
        self,
        node: Any,
        *,
        matcher: _ReferenceKeyMatcher,
        target_value: str,
        path: str = "$",
    ) -> list[str]:
        matched_paths: list[str] = []
        if isinstance(node, dict):
            for key, child in node.items():
                child_path = f"{path}.{key}"
                if matcher.matches(key):
                    matched_paths.extend(
                        self._find_matched_reference_paths(
                            child,
                            value_to_match=target_value,
                            path=child_path,
                        )
                    )
                matched_paths.extend(
                    self._find_reference_paths_in_json_value(
                        child,
                        matcher=matcher,
                        target_value=target_value,
                        path=child_path,
                    )
                )
            return matched_paths
        if isinstance(node, list):
            for index, child in enumerate(node):
                matched_paths.extend(
                    self._find_reference_paths_in_json_value(
                        child,
                        matcher=matcher,
                        target_value=target_value,
                        path=f"{path}[{index}]",
                    )
                )
        return matched_paths

    def _find_matched_reference_paths(
        self,
        child: Any,
        *,
        value_to_match: str,
        path: str,
    ) -> list[str]:
        matched_paths: list[str] = []
        if isinstance(child, str):
            if child == value_to_match:
                matched_paths.append(path)
            return matched_paths
        if isinstance(child, list):
            for index, item in enumerate(child):
                if isinstance(item, str) and item == value_to_match:
                    matched_paths.append(f"{path}[{index}]")
            return matched_paths
        if isinstance(child, dict):
            for dict_key, dict_value in child.items():
                if isinstance(dict_value, str) and dict_value == value_to_match:
                    matched_paths.append(f"{path}.{dict_key}")
        return matched_paths

    def _confirm_content_rename_preview(
        self,
        *,
        title: str,
        old_content_id: str,
        new_content_id: str,
        old_file_path: Path,
        new_file_path: Path,
        reference_updates: list[_JsonReferenceFileUpdate],
    ) -> bool:
        lines = [
            f"Rename {old_content_id} -> {new_content_id}",
            f"Move file: {old_file_path.name} -> {new_file_path.name}",
            "",
        ]
        if reference_updates:
            lines.append("Reference updates:")
            for update in reference_updates:
                display_path = update.file_path.name
                joined_paths = ", ".join(update.changed_paths)
                lines.append(f"- {display_path}: {joined_paths}")
        else:
            lines.append("No known reference updates were detected.")
        detail_text = "\n".join(lines)
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText("Apply this rename/move and the previewed reference updates?")
        dialog.setDetailedText(detail_text)
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.Ok)
        return dialog.exec() == int(QMessageBox.StandardButton.Ok)

    def _confirm_content_delete_preview(
        self,
        *,
        title: str,
        content_id: str,
        file_path: Path,
        reference_usages: list[_JsonReferenceUsage],
    ) -> bool:
        lines = [
            f"Delete {content_id}",
            f"Delete file: {file_path.name}",
            "",
        ]
        if reference_usages:
            lines.append("Known references/usages will be left broken:")
            for usage in reference_usages:
                display_path = usage.file_path.name
                joined_paths = ", ".join(usage.matched_paths)
                lines.append(f"- {display_path}: {joined_paths}")
        else:
            lines.append("No known references/usages were detected.")
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText("Delete this content file and leave any known references unchanged?")
        dialog.setInformativeText("The project may fail startup validation or break later until those references are fixed.")
        dialog.setDetailedText("\n".join(lines))
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return dialog.exec() == int(QMessageBox.StandardButton.Ok)

    def _confirm_folder_move_preview(
        self,
        *,
        title: str,
        old_relative_path: str,
        new_relative_path: str,
        moved_files: list[Path],
        reference_updates: list[_JsonReferenceFileUpdate],
    ) -> bool:
        lines = [
            f"Move folder {old_relative_path} -> {new_relative_path}",
            f"Move {len(moved_files)} file(s).",
            "",
        ]
        if reference_updates:
            lines.append("Reference updates:")
            for update in reference_updates:
                display_path = update.file_path.name
                joined_paths = ", ".join(update.changed_paths)
                lines.append(f"- {display_path}: {joined_paths}")
        else:
            lines.append("No known reference updates were detected.")
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText("Apply this folder move and the previewed reference updates?")
        dialog.setDetailedText("\n".join(lines))
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.Ok)
        return dialog.exec() == int(QMessageBox.StandardButton.Ok)

    def _confirm_global_entity_rename_preview(
        self,
        *,
        old_entity_id: str,
        new_entity_id: str,
        reference_updates: list[_JsonReferenceFileUpdate],
    ) -> bool:
        lines = [
            f"Rename global entity id {old_entity_id} -> {new_entity_id}",
            "",
        ]
        if reference_updates:
            lines.append("Reference updates:")
            for update in reference_updates:
                display_path = update.file_path.name
                joined_paths = ", ".join(update.changed_paths)
                lines.append(f"- {display_path}: {joined_paths}")
        else:
            lines.append("No known reference updates were detected.")
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Rename Global Entity ID")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText("Apply this global entity rename and the previewed reference updates?")
        dialog.setDetailedText("\n".join(lines))
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.Ok)
        return dialog.exec() == int(QMessageBox.StandardButton.Ok)

    def _confirm_global_entity_delete_preview(
        self,
        *,
        entity_id: str,
        reference_usages: list[_JsonReferenceUsage],
    ) -> bool:
        lines = [
            f"Delete global entity id {entity_id}",
            "",
        ]
        if reference_usages:
            lines.append("Known references/usages will be left broken:")
            for usage in reference_usages:
                display_path = usage.file_path.name
                joined_paths = ", ".join(usage.matched_paths)
                lines.append(f"- {display_path}: {joined_paths}")
        else:
            lines.append("No known references/usages were detected.")
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Delete Global Entity")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText("Delete this global entity and leave any known references unchanged?")
        dialog.setInformativeText("The project may fail startup validation or break later until those references are fixed.")
        dialog.setDetailedText("\n".join(lines))
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return dialog.exec() == int(QMessageBox.StandardButton.Ok)

    def _area_entity_reference_matcher(self) -> _ReferenceKeyMatcher:
        return _ReferenceKeyMatcher(
            exact_keys=frozenset(
                {
                    "entity_id",
                    "source_entity_id",
                    "actor_id",
                    "caller_id",
                    "target_id",
                    "follow_entity_id",
                    "exclude_entity_id",
                    "transfer_entity_id",
                    "entity_ids",
                    "transfer_entity_ids",
                    "input_targets",
                }
            ),
            suffix_keys=frozenset({"_entity_id", "_entity_ids"}),
        )

    def _build_area_entity_source_update(
        self,
        doc: AreaDocument,
        *,
        old_entity_id: str,
        updated_entity: EntityDocument,
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        area_data = doc.to_dict()
        raw_entities = area_data.get("entities", [])
        if not isinstance(raw_entities, list):
            raise ValueError("Area JSON must keep entities as an array.")
        target_index: int | None = None
        for index, raw_entity in enumerate(raw_entities):
            if not isinstance(raw_entity, dict):
                continue
            if str(raw_entity.get("id", "")).strip() == old_entity_id:
                raw_entities[index] = updated_entity.to_dict()
                target_index = index
                break
        if target_index is None:
            raise ValueError(f"Could not locate entity '{old_entity_id}' in the source area.")
        return area_data, (f"$.entities[{target_index}]",)

    def _confirm_entity_rename_preview(
        self,
        *,
        area_id: str,
        old_entity_id: str,
        new_entity_id: str,
        reference_updates: list[_JsonReferenceFileUpdate],
    ) -> bool:
        lines = [
            f"Rename entity {old_entity_id} -> {new_entity_id}",
            f"Source area: {area_id}",
            "",
        ]
        if reference_updates:
            lines.append("Reference updates:")
            for update in reference_updates:
                display_path = update.file_path.name
                joined_paths = ", ".join(update.changed_paths)
                lines.append(f"- {display_path}: {joined_paths}")
        else:
            lines.append("Only the source entity id will change.")
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Rename Area Entity")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText("Apply this entity rename and the previewed reference updates?")
        dialog.setDetailedText("\n".join(lines))
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.Ok)
        return dialog.exec() == int(QMessageBox.StandardButton.Ok)

    def _apply_area_entity_rename_refactor(
        self,
        *,
        content_id: str,
        doc: AreaDocument,
        current: EntityDocument,
        updated: EntityDocument,
        status_message: str,
    ) -> bool:
        if self._manifest is None:
            return False
        info = self._tab_widget.content_info(content_id)
        if info is None:
            return False
        source_file_path = info.file_path.resolve()
        other_dirty_ids = [
            dirty_id
            for dirty_id in self._tab_widget.dirty_content_ids()
            if dirty_id != content_id
        ]
        if not self._maybe_save_dirty_tabs(other_dirty_ids):
            return False
        source_data, base_paths = self._build_area_entity_source_update(
            doc,
            old_entity_id=current.id,
            updated_entity=updated,
        )
        matcher = self._area_entity_reference_matcher()
        source_updated_data, source_reference_paths = self._replace_reference_keys_in_json_value(
            source_data,
            old_value=current.id,
            new_value=updated.id,
            matcher=matcher,
        )
        source_update = _JsonReferenceFileUpdate(
            file_path=source_file_path,
            updated_text=f"{format_json_for_editor(source_updated_data)}\n",
            changed_paths=tuple((*base_paths, *source_reference_paths)),
        )
        other_updates = self._collect_reference_updates(
            old_value=current.id,
            new_value=updated.id,
            matcher=matcher,
            skip_files={source_file_path},
        )
        reference_updates = [source_update, *other_updates]
        if not self._confirm_entity_rename_preview(
            area_id=content_id,
            old_entity_id=current.id,
            new_entity_id=updated.id,
            reference_updates=reference_updates,
        ):
            return False
        try:
            for update in reference_updates:
                update.file_path.write_text(update.updated_text, encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Rename Failed",
                f"Could not rename entity '{current.id}':\n{exc}",
            )
            return False
        self._tab_widget.close_all()
        self._area_docs.clear()
        self._json_dirty_bound.clear()
        self._refresh_project_metadata_surfaces()
        self._refresh_area_panel()
        self._open_area(content_id, source_file_path)
        self._area_panel.highlight_area(content_id)
        self._active_instance_entity_id = updated.id
        reopened_context = self._active_area_context()
        if reopened_context is not None:
            _area_id, _reloaded_doc, reloaded_canvas = reopened_context
            reloaded_canvas.set_selected_entity(
                updated.id,
                cycle_position=1,
                cycle_total=1,
                emit=False,
            )
        self._refresh_render_properties_target()
        self._refresh_entity_instance_panel()
        self._sync_json_edit_actions()
        self._update_paint_status()
        self.statusBar().showMessage(status_message, 2500)
        return True

    # ------------------------------------------------------------------
    # Slots — view menu
    # ------------------------------------------------------------------

    def _on_grid_toggled(self, visible: bool) -> None:
        canvas = self._active_canvas()
        if canvas is not None:
            canvas.set_grid_visible(visible)

    def _on_entities_visibility_toggled(self, visible: bool) -> None:
        self._entities_visible = visible
        canvas = self._active_canvas()
        if canvas is not None:
            canvas.set_entities_visible(visible)

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
        if enabled and self._tile_select_action.isChecked():
            self._set_tile_select_action_state(False)
            canvas.set_tile_select_mode(False)
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
        self._refresh_tile_selection_actions()

    def _on_select_toggled(self, enabled: bool) -> None:
        canvas = self._active_canvas()
        if canvas is None:
            self._set_select_action_state(False)
            return
        if enabled and self._paint_tiles_action.isChecked():
            self._set_paint_tiles_action_state(False)
            canvas.set_tile_paint_mode(False)
        if enabled and self._tile_select_action.isChecked():
            self._set_tile_select_action_state(False)
            canvas.set_tile_select_mode(False)
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
        self._refresh_tile_selection_actions()

    def _on_tile_select_toggled(self, enabled: bool) -> None:
        canvas = self._active_canvas()
        if canvas is None:
            self._set_tile_select_action_state(False)
            return
        if enabled and self._paint_tiles_action.isChecked():
            self._set_paint_tiles_action_state(False)
            canvas.set_tile_paint_mode(False)
        if enabled and self._select_action.isChecked():
            self._set_select_action_state(False)
            canvas.set_select_mode(False)
        if enabled and self._cell_flags_action.isChecked():
            self._set_cell_flags_action_state(False)
            canvas.set_cell_flags_edit_mode(False)
        canvas.set_tile_select_mode(enabled)
        if enabled:
            self._update_paint_status()
            self.statusBar().showMessage(
                "Tile Select mode: drag to select tiles on the active layer, Delete clears, Ctrl+C/X/V copy cut and paste.",
                4000,
            )
        else:
            self._update_paint_status()
        self._refresh_tile_selection_actions()

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
        if enabled and self._tile_select_action.isChecked():
            self._set_tile_select_action_state(False)
            canvas.set_tile_select_mode(False)
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
        self._refresh_tile_selection_actions()

    def _on_tile_selected(self, gid: int) -> None:
        canvas = self._active_canvas()
        if canvas is not None:
            canvas.set_selected_gid_block(self._tileset_panel.selected_brush_block)
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
        self._refresh_layer_action_state()
        self._update_paint_status()

    def _on_add_tile_layer_requested(self) -> None:
        context = self._active_area_context()
        if context is None:
            return
        content_id, doc, canvas = context
        width, height = layer_dimensions(doc)
        if width <= 0 or height <= 0:
            QMessageBox.warning(
                self,
                "Add Tile Layer",
                "This area has no known tile-layer dimensions yet, so the editor cannot create a new layer safely.",
            )
            return
        layer_name = self._prompt_tile_layer_name("Add Tile Layer")
        if not layer_name:
            return
        index = add_tile_layer(doc, name=layer_name, width=width, height=height)
        canvas.refresh_scene_contents()
        self._layer_panel.set_layers(doc.tile_layers)
        self._layer_panel.set_active_layer(index)
        canvas.set_active_layer(index)
        self._set_render_target_layer(index)
        self._tab_widget.set_dirty(content_id, True)
        self._paint_tiles_action.setEnabled(bool(doc.tile_layers and doc.tilesets))
        self._tile_select_action.setEnabled(bool(doc.tile_layers))
        self._refresh_layer_action_state()
        self._refresh_tile_selection_actions()
        self._update_paint_status()
        self.statusBar().showMessage(f"Added layer {layer_name}.", 2500)

    def _on_rename_tile_layer_requested(self, index: int) -> None:
        context = self._active_area_context()
        if context is None:
            return
        content_id, doc, _canvas = context
        if not (0 <= index < len(doc.tile_layers)):
            return
        current = doc.tile_layers[index]
        name = self._prompt_tile_layer_name("Rename Tile Layer", current.name)
        if not name or name == current.name:
            return
        rename_tile_layer(doc, index, name)
        self._layer_panel.update_layer(index, doc.tile_layers[index])
        self._tab_widget.set_dirty(content_id, True)
        self._refresh_render_properties_target()
        self._refresh_layer_action_state()
        self._update_paint_status()
        self.statusBar().showMessage(f"Renamed layer to {name}.", 2500)

    def _on_delete_tile_layer_requested(self, index: int) -> None:
        context = self._active_area_context()
        if context is None:
            return
        content_id, doc, canvas = context
        if not (0 <= index < len(doc.tile_layers)):
            return
        layer_name = doc.tile_layers[index].name
        if not self._confirm_tile_layer_delete(layer_name):
            return
        removed = remove_tile_layer(doc, index)
        if removed is None:
            return
        canvas.refresh_scene_contents()
        self._layer_panel.set_layers(doc.tile_layers)
        if doc.tile_layers:
            new_index = min(index, len(doc.tile_layers) - 1)
            self._layer_panel.set_active_layer(new_index)
            canvas.set_active_layer(new_index)
            self._set_render_target_layer(new_index)
        else:
            self._render_target_kind = None
            self._render_target_ref = None
            self._render_panel.clear_target()
            self._status_layer.setText("")
        self._tab_widget.set_dirty(content_id, True)
        self._paint_tiles_action.setEnabled(bool(doc.tile_layers and doc.tilesets))
        self._tile_select_action.setEnabled(bool(doc.tile_layers))
        self._refresh_layer_action_state()
        self._refresh_tile_selection_actions()
        self._update_paint_status()
        self.statusBar().showMessage(f"Deleted layer {layer_name}.", 2500)

    def _on_move_tile_layer_requested(self, index: int, delta: int) -> None:
        context = self._active_area_context()
        if context is None:
            return
        content_id, doc, canvas = context
        target = index + delta
        if not (0 <= index < len(doc.tile_layers)) or not (0 <= target < len(doc.tile_layers)):
            return
        final_index = move_tile_layer(doc, index, target)
        if final_index is None:
            return
        moved_name = doc.tile_layers[final_index].name
        canvas.refresh_scene_contents()
        self._layer_panel.set_layers(doc.tile_layers)
        self._layer_panel.set_active_layer(final_index)
        canvas.set_active_layer(final_index)
        self._set_render_target_layer(final_index)
        self._tab_widget.set_dirty(content_id, True)
        self._refresh_layer_action_state()
        self._update_paint_status()
        self.statusBar().showMessage(f"Moved layer {moved_name}.", 2500)

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

    def _refresh_layer_action_state(self) -> None:
        context = self._active_area_context()
        if context is None:
            self._rename_tile_layer_action.setEnabled(False)
            self._delete_tile_layer_action.setEnabled(False)
            self._move_tile_layer_up_action.setEnabled(False)
            self._move_tile_layer_down_action.setEnabled(False)
            return
        _content_id, doc, _canvas = context
        index = self._layer_panel.active_layer
        has_layers = bool(doc.tile_layers)
        self._rename_tile_layer_action.setEnabled(has_layers and 0 <= index < len(doc.tile_layers))
        self._delete_tile_layer_action.setEnabled(has_layers and 0 <= index < len(doc.tile_layers))
        self._move_tile_layer_up_action.setEnabled(has_layers and index > 0)
        self._move_tile_layer_down_action.setEnabled(has_layers and 0 <= index < (len(doc.tile_layers) - 1))

    def _prompt_tile_layer_name(self, title: str, initial_value: str = "") -> str | None:
        name, ok = QInputDialog.getText(
            self,
            title,
            "Layer name:",
            text=initial_value,
        )
        if not ok:
            return None
        trimmed = name.strip()
        if not trimmed:
            QMessageBox.warning(self, title, "Layer name must not be empty.")
            return None
        return trimmed

    def _confirm_tile_layer_delete(self, layer_name: str) -> bool:
        choice = QMessageBox.question(
            self,
            "Delete Tile Layer",
            f"Delete tile layer '{layer_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return choice == QMessageBox.StandardButton.Yes

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

    def _on_tile_selection_changed(self, _has_selection: bool) -> None:
        self._refresh_tile_selection_actions()
        self._update_paint_status()

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

    def _on_delete_active_selection(self) -> None:
        canvas = self._active_canvas()
        if canvas is None:
            return
        if self._tile_select_action.isChecked():
            self._on_delete_selected_tiles()
            return
        self._on_delete_selected_entity()

    def _on_clear_active_selection(self) -> None:
        canvas = self._active_canvas()
        if canvas is None:
            return
        if self._tile_select_action.isChecked():
            self._on_clear_tile_selection()
            return
        self._on_clear_selection()

    def _on_clear_selection(self) -> None:
        canvas = self._active_canvas()
        if canvas is None or not self._select_action.isChecked():
            return
        if not canvas.selected_entity_id:
            return
        canvas.clear_selected_entity()
        self._refresh_tile_selection_actions()

    def _on_clear_tile_selection(self) -> None:
        canvas = self._active_canvas()
        if canvas is None or not self._tile_select_action.isChecked():
            return
        if not canvas.clear_tile_selection():
            return
        self._refresh_tile_selection_actions()
        self._update_paint_status()
        self.statusBar().showMessage("Cleared tile selection.", 2000)

    def _on_delete_selected_tiles(self) -> None:
        context = self._active_area_context()
        if context is None or not self._tile_select_action.isChecked():
            return
        content_id, _doc, canvas = context
        if not canvas.has_tile_selection:
            return
        if not canvas.clear_selected_tiles():
            return
        self._tab_widget.set_dirty(content_id, True)
        self._refresh_tile_selection_actions()
        self._update_paint_status()
        self.statusBar().showMessage("Cleared selected tiles.", 2500)

    def _on_copy_tiles(self) -> None:
        canvas = self._active_canvas()
        if canvas is None or not self._tile_select_action.isChecked():
            return
        block = canvas.selected_tile_block()
        if block is None:
            return
        self._tile_clipboard = _TileClipboard(
            width=len(block[0]),
            height=len(block),
            grid=tuple(tuple(int(gid) for gid in row) for row in block),
        )
        self._refresh_tile_selection_actions()
        self.statusBar().showMessage(
            f"Copied {self._tile_clipboard.width}x{self._tile_clipboard.height} tile selection.",
            2500,
        )

    def _on_cut_tiles(self) -> None:
        context = self._active_area_context()
        if context is None or not self._tile_select_action.isChecked():
            return
        content_id, _doc, canvas = context
        block = canvas.selected_tile_block()
        if block is None:
            return
        self._tile_clipboard = _TileClipboard(
            width=len(block[0]),
            height=len(block),
            grid=tuple(tuple(int(gid) for gid in row) for row in block),
        )
        if not canvas.clear_selected_tiles():
            return
        self._tab_widget.set_dirty(content_id, True)
        self._refresh_tile_selection_actions()
        self._update_paint_status()
        self.statusBar().showMessage(
            f"Cut {self._tile_clipboard.width}x{self._tile_clipboard.height} tile selection.",
            2500,
        )

    def _on_paste_tiles(self) -> None:
        context = self._active_area_context()
        if context is None or not self._tile_select_action.isChecked() or self._tile_clipboard is None:
            return
        content_id, _doc, canvas = context
        anchor = canvas.preferred_paste_anchor()
        if anchor is None:
            self.statusBar().showMessage("Paste needs a hovered or selected tile anchor.", 2500)
            return
        pasted = canvas.paste_tile_block(
            anchor[0],
            anchor[1],
            [list(row) for row in self._tile_clipboard.grid],
        )
        if pasted is None:
            return
        self._tab_widget.set_dirty(content_id, True)
        self._refresh_tile_selection_actions()
        self._update_paint_status()
        self.statusBar().showMessage(
            f"Pasted {self._tile_clipboard.width}x{self._tile_clipboard.height} tiles.",
            2500,
        )

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
                    self._connected_canvas.tile_selection_changed.disconnect(
                        self._on_tile_selection_changed
                    )
                except (RuntimeError, TypeError):
                    pass
            try:
                self._layer_panel.layer_visibility_changed.disconnect()
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
        canvas.tile_selection_changed.connect(self._on_tile_selection_changed)
        self._layer_panel.layer_visibility_changed.connect(canvas.set_layer_visible)
        canvas.set_entities_visible(self._entities_visible)

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
        content_id: str,
        file_path: Path,
    ) -> None:
        self._add_rename_content_action(menu, ContentType.ASSET, content_id, file_path)
        self._add_delete_content_action(menu, ContentType.ASSET, content_id, file_path)
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

    def _browse_project_asset(self, title: str = "Choose Project Asset") -> str | None:
        if self._manifest is None:
            return None
        start_dir = str(self._manifest.asset_paths[0]) if self._manifest.asset_paths else str(
            self._manifest.project_root
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            title,
            start_dir,
            "Image files (*.png *.webp *.bmp *.jpg *.jpeg);;All files (*)",
        )
        if not path:
            return None
        return self._authored_asset_path_for(Path(path))

    def _browse_project_area_id(self, current_value: str = "") -> str | None:
        if self._manifest is None:
            return None
        return self._browse_known_reference(
            title="Choose Area",
            label="Area",
            values=[entry.area_id for entry in discover_areas(self._manifest)],
            current_value=current_value,
        )

    def _browse_project_entity_id(self, current_value: str = "") -> str | None:
        return self._browse_known_reference(
            title="Choose Entity",
            label="Entity",
            values=sorted(self._project_used_entity_ids()),
            current_value=current_value,
        )

    def _browse_project_item_id(self, current_value: str = "") -> str | None:
        if self._manifest is None:
            return None
        return self._browse_known_reference(
            title="Choose Item",
            label="Item",
            values=[entry.item_id for entry in discover_items(self._manifest)],
            current_value=current_value,
        )

    def _browse_project_dialogue_id(self, current_value: str = "") -> str | None:
        if self._manifest is None:
            return None
        return self._browse_known_reference(
            title="Choose Dialogue",
            label="Dialogue",
            values=self._discover_prefixed_json_content_ids(
                self._manifest.dialogue_paths,
                prefix=_DIALOGUE_ID_PREFIX,
            ),
            current_value=current_value,
        )

    def _browse_project_command_id(self, current_value: str = "") -> str | None:
        if self._manifest is None:
            return None
        return self._browse_known_reference(
            title="Choose Command",
            label="Command",
            values=self._discover_prefixed_json_content_ids(
                self._manifest.command_paths,
                prefix=_COMMAND_ID_PREFIX,
            ),
            current_value=current_value,
        )

    def _browse_known_reference(
        self,
        *,
        title: str,
        label: str,
        values: list[str],
        current_value: str = "",
    ) -> str | None:
        options = [value for value in values if value]
        current = current_value.strip()
        if current and current not in options:
            options.insert(0, current)
        if not options:
            QMessageBox.information(
                self,
                title,
                f"No known {label.lower()} ids are available in this project.",
            )
            return None
        current_index = 0
        if current and current in options:
            current_index = options.index(current)
        selected, accepted = QInputDialog.getItem(
            self,
            title,
            label,
            options,
            current_index,
            False,
        )
        if not accepted:
            return None
        return str(selected).strip() or None

    @staticmethod
    def _discover_prefixed_json_content_ids(root_dirs: list[Path], *, prefix: str) -> list[str]:
        entries: list[str] = []
        seen: set[Path] = set()
        for directory in root_dirs:
            if not directory.is_dir():
                continue
            for file_path in sorted(directory.rglob("*.json")):
                resolved = file_path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                try:
                    relative = resolved.relative_to(directory.resolve())
                except ValueError:
                    relative = resolved.name
                relative_name = str(Path(relative).with_suffix("")).replace("\\", "/")
                entries.append(f"{prefix}/{relative_name}".strip("/"))
        return sorted(entries)

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
                ProjectManifestEditorWidget,
                SharedVariablesEditorWidget,
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

        if self._tile_select_action.isChecked():
            self._status_layer.setText(f"Layer: {self._layer_panel.active_layer_name()}")
            canvas = self._active_canvas()
            if canvas is not None and canvas.has_tile_selection:
                bounds = canvas.tile_selection_bounds()
                if bounds is not None:
                    left, top, right, bottom = bounds
                    self._status_gid.setText(
                        f"Tile Select: ({left}, {top}) to ({right}, {bottom})"
                    )
                    return
            self._status_gid.setText("Tile Select")
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

    def _set_tile_select_action_state(self, enabled: bool) -> None:
        self._tile_select_action.blockSignals(True)
        self._tile_select_action.setChecked(enabled)
        self._tile_select_action.blockSignals(False)

    def _set_json_editing_action_state(self, enabled: bool) -> None:
        self._enable_json_editing_action.blockSignals(True)
        self._enable_json_editing_action.setChecked(enabled)
        self._enable_json_editing_action.blockSignals(False)

    def _refresh_tile_selection_actions(self) -> None:
        canvas = self._active_canvas()
        tile_select_active = canvas is not None and self._tile_select_action.isChecked()
        has_selection = canvas is not None and canvas.has_tile_selection
        has_clipboard = self._tile_clipboard is not None
        self._copy_tiles_action.setEnabled(tile_select_active and has_selection)
        self._cut_tiles_action.setEnabled(tile_select_active and has_selection)
        self._paste_tiles_action.setEnabled(tile_select_active and has_clipboard)

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
        canvas.set_selected_gid_block(self._tileset_panel.selected_brush_block)
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
        if updated.id != current.id:
            return self._apply_area_entity_rename_refactor(
                content_id=content_id,
                doc=doc,
                current=current,
                updated=updated,
                status_message=status_message,
            )
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
        | ProjectManifestEditorWidget
        | SharedVariablesEditorWidget
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
                ProjectManifestEditorWidget,
                SharedVariablesEditorWidget,
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
