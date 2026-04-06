"""Project-content prompt and folder workflows for the main window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QInputDialog, QMessageBox

from area_editor.project_io.project_manifest import AREA_ID_PREFIX
from area_editor.widgets.document_tab_widget import ContentType

from .main_window_helpers import _ReferenceKeyMatcher

_COMMAND_ID_PREFIX = "commands"
_DIALOGUE_ID_PREFIX = "dialogues"


class MainWindowProjectContentMixin:
    """Project-content prompts and folder workflows shared by the main window."""

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
