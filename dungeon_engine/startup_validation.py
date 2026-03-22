"""Helpers for validating a project before launching the game or editor."""

from __future__ import annotations

from dungeon_engine.commands.library import (
    NamedCommandValidationError,
    log_named_command_validation_error,
    validate_project_named_commands,
)


def validate_project_startup(
    project,
    *,
    ui_title: str,
    show_dialog: bool = True,
) -> NamedCommandValidationError | None:
    """Validate project command content and report any startup-blocking errors."""
    try:
        validate_project_named_commands(project)
        return None
    except NamedCommandValidationError as error:
        log_named_command_validation_error(error)
        message = error.format_user_message()
        print(message)
        if show_dialog:
            _show_error_dialog(ui_title, message)
        return error


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

