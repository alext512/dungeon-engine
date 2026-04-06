"""Project-content reference scanning and refactor workflows for the main window."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QMessageBox

from area_editor.documents.area_document import AreaDocument, EntityDocument
from area_editor.json_format import format_json_for_editor
from area_editor.project_io.project_manifest import (
    discover_areas,
    discover_entity_templates,
)
from area_editor.widgets.document_tab_widget import ContentType
from area_editor.widgets.file_tree_panel import FileTreePanel

from .main_window_helpers import (
    _JsonReferenceFileUpdate,
    _JsonReferenceUsage,
    _ReferenceKeyMatcher,
)


class MainWindowProjectRefactorMixin:
    """Shared reference and preview workflows used by project-content actions."""

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
        dialog.setInformativeText(
            "The project may fail startup validation or break later until those references are fixed."
        )
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
        dialog.setText(
            "Apply this global entity rename and the previewed reference updates?"
        )
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
        dialog.setInformativeText(
            "The project may fail startup validation or break later until those references are fixed."
        )
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
