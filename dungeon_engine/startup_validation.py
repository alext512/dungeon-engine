"""Helpers for validating a project before launch."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dungeon_engine.commands.library import (
    ProjectCommandValidationError,
    log_project_command_validation_error,
    validate_project_commands,
)
from dungeon_engine.items import (
    ItemDefinitionValidationError,
    log_item_definition_validation_error,
    validate_project_items,
)
from dungeon_engine.world.loader import (
    AreaValidationError,
    EntityTemplateValidationError,
    instantiate_entity,
    load_area_from_data,
    log_area_validation_error,
    log_entity_template_validation_error,
    validate_project_areas,
    validate_project_entity_templates,
)
from dungeon_engine.logging_utils import get_logger

logger = get_logger(__name__)


class StaticReferenceValidationError(ValueError):
    """Raised when statically resolvable authored references are broken at startup."""

    def __init__(self, project_root: Path, issues: list[str]) -> None:
        self.project_root = project_root
        self.issues = list(issues)
        super().__init__(
            f"Static reference validation failed for '{project_root}' with {len(self.issues)} issue(s)."
        )

    def format_user_message(self, *, max_issues: int = 8) -> str:
        shown_issues = self.issues[:max_issues]
        lines = [
            f"Static reference validation failed with {len(self.issues)} issue(s).",
            "See logs/error.log for full details.",
            "",
            "First issues:",
        ]
        lines.extend(f"- {issue}" for issue in shown_issues)
        hidden_count = len(self.issues) - len(shown_issues)
        if hidden_count > 0:
            lines.append(f"- ...and {hidden_count} more")
        return "\n".join(lines)


def validate_project_startup(
    project,
    *,
    ui_title: str,
    show_dialog: bool = True,
) -> (
    ProjectCommandValidationError
    | ItemDefinitionValidationError
    | EntityTemplateValidationError
    | AreaValidationError
    | StaticReferenceValidationError
    | None
):
    """Validate project content and report any startup-blocking errors."""
    # Validate entity templates.
    try:
        validate_project_entity_templates(project)
    except EntityTemplateValidationError as error:
        log_entity_template_validation_error(error)
        message = error.format_user_message()
        print(message)
        if show_dialog:
            _show_error_dialog(ui_title, message)
        return error

    # Validate item definitions.
    try:
        validate_project_items(project)
    except ItemDefinitionValidationError as error:
        log_item_definition_validation_error(error)
        message = error.format_user_message()
        print(message)
        if show_dialog:
            _show_error_dialog(ui_title, message)
        return error

    # Validate areas.
    try:
        validate_project_areas(project)
    except AreaValidationError as error:
        log_area_validation_error(error)
        message = error.format_user_message()
        print(message)
        if show_dialog:
            _show_error_dialog(ui_title, message)
        return error

    # Validate project commands.
    try:
        validate_project_commands(project)
    except ProjectCommandValidationError as error:
        log_project_command_validation_error(error)
        message = error.format_user_message()
        print(message)
        if show_dialog:
            _show_error_dialog(ui_title, message)
        return error

    try:
        validate_project_static_references(project)
        return None
    except StaticReferenceValidationError as error:
        log_static_reference_validation_error(error)
        message = error.format_user_message()
        print(message)
        if show_dialog:
            _show_error_dialog(ui_title, message)
        return error


def validate_project_static_references(project) -> None:
    """Validate statically resolvable authored dialogue/asset references."""
    issues: list[str] = []
    for file_path in _iter_static_reference_scan_files(project):
        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(
                f"{file_path}: invalid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})."
            )
            continue
        except Exception as exc:
            issues.append(f"{file_path}: could not be read for static reference validation ({exc}).")
            continue
        issues.extend(
            _collect_static_reference_issues(
                raw,
                project=project,
                source_name=str(file_path),
            )
        )

    for area_path in project.list_area_files():
        try:
            raw = json.loads(area_path.read_text(encoding="utf-8"))
            area, world = load_area_from_data(
                raw,
                source_name=str(area_path),
                asset_manager=None,
                project=project,
            )
        except Exception:
            continue
        issues.extend(
            _collect_loaded_area_reference_issues(
                area,
                world,
                project=project,
                source_name=str(area_path),
            )
        )

    for index, entity_data in enumerate(project.global_entities):
        source_name = f"project.json global_entities[{index}]"
        try:
            entity = instantiate_entity(
                {
                    **entity_data,
                    "scope": "global",
                },
                16,
                project=project,
                source_name=source_name,
            )
        except Exception:
            continue
        issues.extend(
            _collect_loaded_entity_reference_issues(
                entity,
                project=project,
                source_name=source_name,
            )
        )

    issues = list(dict.fromkeys(issues))
    if issues:
        raise StaticReferenceValidationError(project.project_root, issues)


def log_static_reference_validation_error(error: StaticReferenceValidationError) -> None:
    """Write a full static-reference validation failure report to the persistent log."""
    logger.error(
        "Static reference validation failed for %s with %d issue(s):\n%s",
        error.project_root,
        len(error.issues),
        "\n".join(f"- {issue}" for issue in error.issues),
    )


def _iter_static_reference_scan_files(project) -> list[Path]:
    files: list[Path] = [project.project_root / "project.json"]
    if project.shared_variables_path is not None and project.shared_variables_path.is_file():
        files.append(project.shared_variables_path.resolve())
    for root_list in (
        project.entity_template_paths,
        project.area_paths,
        project.command_paths,
        project.item_paths,
        project.asset_paths,
    ):
        for root_dir in root_list:
            if not root_dir.is_dir():
                continue
            files.extend(path.resolve() for path in sorted(root_dir.rglob("*.json")))
    dialogue_root = (project.project_root / "dialogues").resolve()
    if dialogue_root.is_dir():
        files.extend(path.resolve() for path in sorted(dialogue_root.rglob("*.json")))

    unique: list[Path] = []
    seen: set[Path] = set()
    for file_path in files:
        resolved = file_path.resolve()
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def _collect_static_reference_issues(
    value: Any,
    *,
    project,
    source_name: str,
    path: str = "$",
    current_key: str | None = None,
) -> list[str]:
    issues: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            issues.extend(
                _collect_static_reference_issues(
                    child,
                    project=project,
                    source_name=source_name,
                    path=f"{path}.{key}",
                    current_key=str(key),
                )
            )
        return issues
    if isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(
                _collect_static_reference_issues(
                    child,
                    project=project,
                    source_name=source_name,
                    path=f"{path}[{index}]",
                    current_key=current_key,
                )
            )
        return issues
    if not isinstance(value, str):
        return issues

    resolved = value.strip()
    if not resolved or resolved.startswith("$"):
        return issues
    if _is_dialogue_reference_key(current_key):
        if not _dialogue_reference_exists(project, resolved):
            issues.append(f"{source_name} ({path}): missing dialogue '{resolved}'.")
        return issues
    if _is_asset_reference_key(current_key):
        if project.resolve_asset(resolved) is None:
            issues.append(f"{source_name} ({path}): missing asset '{resolved}'.")
        return issues
    return issues


def _collect_loaded_area_reference_issues(area, world, *, project, source_name: str) -> list[str]:
    payload = {
        "tilesets": [{"path": tileset.path} for tileset in area.tilesets],
        "enter_commands": area.enter_commands,
        "entities": [
            _entity_reference_payload(entity)
            for entity in world.iter_entities(include_absent=True)
        ],
    }
    return _collect_static_reference_issues(
        payload,
        project=project,
        source_name=source_name,
    )


def _collect_loaded_entity_reference_issues(entity, *, project, source_name: str) -> list[str]:
    return _collect_static_reference_issues(
        _entity_reference_payload(entity),
        project=project,
        source_name=source_name,
    )


def _entity_reference_payload(entity) -> dict[str, Any]:
    return {
        "visuals": [{"path": visual.path} for visual in entity.visuals],
        "entity_commands": {
            command_id: {"commands": definition.commands}
            for command_id, definition in entity.entity_commands.items()
        },
    }


def _is_dialogue_reference_key(key: str | None) -> bool:
    if key is None:
        return False
    return key == "dialogue_path" or key.endswith("_dialogue_path")


def _is_asset_reference_key(key: str | None) -> bool:
    if key is None:
        return False
    if _is_dialogue_reference_key(key):
        return False
    if key in {"save_path", "shared_variables_path"}:
        return False
    return key in {"path", "atlas"} or key.endswith("_path")


def _dialogue_reference_exists(project, reference: str) -> bool:
    resolved_path = Path(reference)
    if not resolved_path.is_absolute():
        resolved_path = (project.project_root / resolved_path).resolve()
    return resolved_path.is_file()


def _show_error_dialog(title: str, message: str) -> None:
    """Show a best-effort blocking error dialog without crashing on UI failures."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message, parent=root)
        root.destroy()
    except Exception:
        return
