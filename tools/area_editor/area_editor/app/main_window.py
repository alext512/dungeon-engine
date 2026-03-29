"""Main application window.

Hosts a tabbed document area as the central widget and docks content
browser panels on the left and the layer panel on the right.  Wires
menus, status bar, and cross-widget signals.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
)

from area_editor.catalogs.template_catalog import TemplateCatalog
from area_editor.catalogs.tileset_catalog import TilesetCatalog
from area_editor.documents.area_document import (
    AreaDocument,
    load_area_document,
    save_area_document,
)
from area_editor.project_io.asset_resolver import AssetResolver
from area_editor.project_io.manifest import (
    ProjectManifest,
    discover_areas,
    load_manifest,
)
from area_editor.widgets.area_list_panel import AreaListPanel
from area_editor.widgets.document_tab_widget import ContentType, DocumentTabWidget
from area_editor.widgets.file_tree_panel import FileTreePanel
from area_editor.widgets.layer_list_panel import LayerListPanel
from area_editor.widgets.template_list_panel import TemplateListPanel
from area_editor.widgets.tile_canvas import TileCanvas
from area_editor.widgets.tileset_browser_panel import TilesetBrowserPanel

_SETTINGS_KEY_LAST_PROJECT = "last_project_path"

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Top-level editor window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Area Editor")
        self.setMinimumSize(640, 480)
        self._size_to_screen()
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

        # Central tabbed document area
        self._tab_widget = DocumentTabWidget()
        self.setCentralWidget(self._tab_widget)

        # Dock panels — left side: project content browser tabs
        self._area_panel = AreaListPanel()
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._area_panel)

        self._template_panel = TemplateListPanel()
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._template_panel)

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

        self._tileset_panel = TilesetBrowserPanel()
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._tileset_panel)

        # Stack all content browsers as tabs in the left dock
        self.tabifyDockWidget(self._area_panel, self._template_panel)
        self.tabifyDockWidget(self._template_panel, self._dialogue_panel)
        self.tabifyDockWidget(self._dialogue_panel, self._command_panel)
        self.tabifyDockWidget(self._command_panel, self._asset_panel)
        self._area_panel.raise_()  # show area list tab by default

        # Settings
        self._settings = QSettings("PuzzleDungeon", "AreaEditor")

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
        self._dialogue_panel.file_open_requested.connect(
            lambda cid, fp: self._open_content(cid, fp, ContentType.DIALOGUE)
        )
        self._command_panel.file_open_requested.connect(
            lambda cid, fp: self._open_content(cid, fp, ContentType.NAMED_COMMAND)
        )
        self._asset_panel.file_open_requested.connect(
            lambda cid, fp: self._open_content(cid, fp, ContentType.ASSET)
        )

        # Tab widget signals
        self._tab_widget.active_tab_changed.connect(self._on_active_tab_changed)
        self._tab_widget.tab_close_requested.connect(self._on_tab_close_requested)
        self._tab_widget.tab_closed.connect(self._on_tab_closed)

        # Tileset browser + layer panel signals
        self._tileset_panel.tile_selected.connect(self._on_tile_selected)
        self._layer_panel.active_layer_changed.connect(self._on_active_layer_changed)

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

        # Close all existing tabs
        self._tab_widget.close_all()
        self._area_docs.clear()
        self._connected_canvas = None
        self._layer_panel.clear_layers()

        areas = discover_areas(self._manifest)
        self._area_panel.set_areas(areas)
        self._template_panel.set_templates(
            self._manifest, self._templates, self._catalog
        )
        self._dialogue_panel.populate(self._manifest.dialogue_paths)
        self._command_panel.populate(self._manifest.command_paths)
        self._asset_panel.populate(self._manifest.asset_paths)

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

        edit_menu = self.menuBar().addMenu("&Edit")

        self._paint_tiles_action = QAction("Paint &Tiles", self)
        self._paint_tiles_action.setCheckable(True)
        self._paint_tiles_action.setEnabled(False)
        self._paint_tiles_action.setShortcut(QKeySequence("P"))
        self._paint_tiles_action.toggled.connect(self._on_paint_tiles_toggled)
        edit_menu.addAction(self._paint_tiles_action)

        self._cell_flags_action = QAction("Edit Cell &Flags", self)
        self._cell_flags_action.setCheckable(True)
        self._cell_flags_action.setEnabled(False)
        self._cell_flags_action.toggled.connect(self._on_cell_flags_toggled)
        edit_menu.addAction(self._cell_flags_action)

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

    # ------------------------------------------------------------------
    # Slots — side panel open requests
    # ------------------------------------------------------------------

    def _on_area_open_requested(self, area_id: str, file_path: Path) -> None:
        self._open_area(area_id, file_path)

    def _open_content(
        self, content_id: str, file_path: Path, content_type: ContentType
    ) -> None:
        """Open a non-area content item in a tab."""
        self._tab_widget.open_tab(content_id, file_path, content_type)

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

            # Populate tileset browser for this area
            if self._catalog is not None:
                self._tileset_panel.set_tilesets(doc.tilesets, self._catalog)

            # Reconnect layer visibility signals to the active canvas
            canvas = self._active_canvas()
            if canvas is not None:
                self._layer_panel.set_active_layer(canvas.active_layer)
                self._tileset_panel.select_gid(canvas.selected_gid)
                self._connect_canvas(canvas)
                can_paint = bool(doc.tile_layers and doc.tilesets)
                self._paint_tiles_action.setEnabled(can_paint)
                self._set_cell_flags_action_state(canvas.cell_flags_edit_mode)
                self._set_paint_tiles_action_state(canvas.tile_paint_mode)
                self._status_zoom.setText(f"{canvas.zoom_level:.0%}")
                if canvas.tile_paint_mode and can_paint:
                    self._update_paint_status()
                else:
                    self._status_layer.setText("")
                    self._status_gid.setText("")
        elif content_id:
            self._layer_panel.clear_layers()
            self._tileset_panel.clear_tilesets()
            self._status_area.setText(content_id)
            self._status_cell.setText("")
            self._status_layer.setText("")
            self._status_gid.setText("")
            self._status_zoom.setText("")
            self._save_action.setEnabled(False)
            self._cell_flags_action.setEnabled(False)
            self._paint_tiles_action.setEnabled(False)
            self._set_cell_flags_action_state(False)
            self._set_paint_tiles_action_state(False)
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
            self._set_cell_flags_action_state(False)
            self._set_paint_tiles_action_state(False)

    def _on_tab_close_requested(self, content_id: str, _content_type: object) -> None:
        if not self._maybe_save_dirty_tabs([content_id]):
            return
        self._tab_widget.close_content(content_id)

    def _on_tab_closed(self, content_id: str) -> None:
        self._area_docs.pop(content_id, None)

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
        # Mutually exclusive with cell-flag mode
        if enabled and self._cell_flags_action.isChecked():
            self._set_cell_flags_action_state(False)
            canvas.set_cell_flags_edit_mode(False)
        canvas.set_tile_paint_mode(enabled)
        if enabled:
            self._tileset_panel.show()
            self._tileset_panel.raise_()
            self._update_paint_status()
            self.statusBar().showMessage(
                "Paint mode: left-click paint, right-click erase, Alt+click eyedrop.",
                4000,
            )
        else:
            self._status_layer.setText("")
            self._status_gid.setText("")

    def _on_cell_flags_toggled(self, enabled: bool) -> None:
        canvas = self._active_canvas()
        if canvas is None:
            self._set_cell_flags_action_state(False)
            return
        # Mutually exclusive with paint mode
        if enabled and self._paint_tiles_action.isChecked():
            self._set_paint_tiles_action_state(False)
            canvas.set_tile_paint_mode(False)
            self._status_layer.setText("")
            self._status_gid.setText("")
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
        self._status_gid.setText(f"GID: {gid}" if gid else "Eraser")

    def _on_active_layer_changed(self, index: int) -> None:
        canvas = self._active_canvas()
        if canvas is not None:
            canvas.set_active_layer(index)
        self._status_layer.setText(f"Layer: {self._layer_panel.active_layer_name()}")

    def _on_save_active(self) -> None:
        info = self._tab_widget.active_info()
        if info is None or info.content_type != ContentType.AREA:
            return
        if self._save_area(info.content_id):
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
        canvas.set_area(doc, self._catalog, self._templates)
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
                self._layer_panel.layer_visibility_changed.disconnect()
            except (RuntimeError, TypeError):
                pass
            try:
                self._layer_panel.entities_visibility_changed.disconnect()
            except (RuntimeError, TypeError):
                pass

        self._connected_canvas = canvas
        canvas.cell_hovered.connect(self._on_cell_hovered)
        canvas.zoom_changed.connect(self._on_zoom_changed)
        canvas.cell_flag_edited.connect(self._on_cell_flag_edited)
        canvas.tile_painted.connect(self._on_tile_painted)
        canvas.tile_eyedropped.connect(self._on_tile_eyedropped)
        self._layer_panel.layer_visibility_changed.connect(canvas.set_layer_visible)
        self._layer_panel.entities_visibility_changed.connect(
            canvas.set_entities_visible
        )

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
            if not self._save_area(content_id):
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
        self._status_gid.setText(f"GID: {gid}" if gid else "Eraser")

    def _update_paint_status(self) -> None:
        """Update status bar with current paint-mode info."""
        self._status_layer.setText(f"Layer: {self._layer_panel.active_layer_name()}")
        gid = self._tileset_panel.selected_gid
        self._status_gid.setText(f"GID: {gid}" if gid else "Eraser")

    def _set_cell_flags_action_state(self, enabled: bool) -> None:
        self._cell_flags_action.blockSignals(True)
        self._cell_flags_action.setChecked(enabled)
        self._cell_flags_action.blockSignals(False)

    def _set_paint_tiles_action_state(self, enabled: bool) -> None:
        self._paint_tiles_action.blockSignals(True)
        self._paint_tiles_action.setChecked(enabled)
        self._paint_tiles_action.blockSignals(False)
