"""Project-scoped save/load helpers for the play runtime."""

from __future__ import annotations

import copy
from pathlib import Path

from dungeon_engine.world.persistence import (
    apply_current_global_state,
    apply_persistent_area_state,
    capture_current_area_state,
    capture_current_global_state,
)


class GameSaveRuntimeMixin:
    """Provide save-slot dialogs plus save/load session restore helpers for ``Game``."""

    def request_load_game(self, save_path: str | None = None) -> None:
        """Queue a save-slot load so it applies at the scene-boundary phase."""
        resolved_save_path = (
            self._resolve_save_slot_path(save_path)
            if save_path is not None
            else self._prompt_for_load_save_path()
        )
        if resolved_save_path is None:
            return
        self._pending_load_save_path = resolved_save_path
        self._pending_area_change_request = None
        self._pending_new_game_request = None
        self._request_scene_boundary()

    def save_game(self, save_path: str | None = None) -> bool:
        """Open a project-scoped save dialog or write to an explicit save path."""
        resolved_save_path = (
            self._resolve_save_slot_path(save_path)
            if save_path is not None
            else self._prompt_for_save_save_path()
        )
        if resolved_save_path is None:
            return False
        self._write_save_slot(resolved_save_path)
        return True

    def _project_save_dir(self) -> Path:
        """Return the active project's save-root directory, creating it when needed."""
        save_dir = self.project.save_dir
        save_dir.mkdir(parents=True, exist_ok=True)
        return save_dir.resolve()

    def _resolve_save_slot_path(self, save_path: str | Path) -> Path:
        """Resolve and validate a save-slot path inside the active project's save directory."""
        raw_path = Path(save_path)
        save_dir = self._project_save_dir()
        candidate = raw_path if raw_path.is_absolute() else save_dir / raw_path
        if candidate.suffix.lower() != ".json":
            candidate = candidate.with_suffix(".json")
        resolved = candidate.resolve()
        try:
            resolved.relative_to(save_dir)
        except ValueError as exc:
            raise ValueError(
                f"Save path '{resolved}' must stay inside '{save_dir}'."
            ) from exc
        return resolved

    def _default_save_slot_name(self) -> str:
        """Return a sensible default file name for project-scoped save dialogs."""
        current_save_path = self.persistence_runtime.save_path
        if current_save_path is not None:
            try:
                current_save_path.resolve().relative_to(self._project_save_dir())
                return current_save_path.name
            except ValueError:
                pass
        return "save_1.json"

    def _prompt_for_save_save_path(self) -> Path | None:
        """Open a Save As dialog rooted to the active project's save directory."""
        if self.headless:
            raise ValueError("save_game without an explicit save_path is unavailable in headless mode.")

        import tkinter as tk
        from tkinter import filedialog

        save_dir = self._project_save_dir()
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.asksaveasfilename(
            title="Save game",
            initialdir=str(save_dir),
            initialfile=self._default_save_slot_name(),
            defaultextension=".json",
            filetypes=[("JSON save files", "*.json"), ("All files", "*.*")],
        )
        root.destroy()
        if not file_path:
            return None
        return self._resolve_save_slot_path(Path(file_path))

    def _prompt_for_load_save_path(self) -> Path | None:
        """Open a load dialog rooted to the active project's save directory."""
        if self.headless:
            raise ValueError("load_game without an explicit save_path is unavailable in headless mode.")

        import tkinter as tk
        from tkinter import filedialog

        save_dir = self._project_save_dir()
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.askopenfilename(
            title="Load game",
            initialdir=str(save_dir),
            initialfile=self._default_save_slot_name(),
            filetypes=[("JSON save files", "*.json"), ("All files", "*.*")],
        )
        root.destroy()
        if not file_path:
            return None
        return self._resolve_save_slot_path(Path(file_path))

    def _capture_current_area_reference(self) -> str:
        """Return a stable project-relative reference for the currently loaded area."""
        return self.project.area_path_to_reference(self.area_path)

    def _write_save_slot(self, save_path: Path) -> None:
        """Write the current persistent/session state to one explicit save slot."""
        traveler_baseline = copy.deepcopy(self.persistence_runtime.save_data.travelers)
        self.persistence_runtime.refresh_live_travelers(
            self.area,
            self.world,
            include_transient=True,
        )
        _, persistent_reference_world = self._build_current_play_reference()
        self.persistence_runtime.save_data.current_area = self._capture_current_area_reference()
        self.persistence_runtime.save_data.current_input_targets = copy.deepcopy(
            self.world.input_targets
        )
        self.persistence_runtime.save_data.current_camera = (
            None
            if self.camera is None
            else copy.deepcopy(self.camera.to_state_dict())
        )
        self.persistence_runtime.save_data.current_area_state = capture_current_area_state(
            self.area,
            persistent_reference_world,
            self.world,
            project=self.project,
        )
        self.persistence_runtime.save_data.current_global_entities = capture_current_global_state(
            self.area,
            persistent_reference_world,
            self.world,
            project=self.project,
        )
        self.persistence_runtime.set_save_path(save_path)
        try:
            self.persistence_runtime.flush(force=True)
        finally:
            self.persistence_runtime.save_data.travelers = traveler_baseline
            # The exact saved room state is for file output and one-time load restore only.
            self.persistence_runtime.save_data.current_camera = None
            self.persistence_runtime.save_data.current_area_state = None
            self.persistence_runtime.save_data.current_global_entities = None

    def _load_save_slot(self, save_path: Path) -> None:
        """Load one explicit save slot and rebuild the runtime from its saved session."""
        self.persistence_runtime.set_save_path(save_path)
        if not self.persistence_runtime.reload_from_disk():
            raise FileNotFoundError(f"Save file '{save_path}' was not found.")

        current_area_state = copy.deepcopy(self.persistence_runtime.save_data.current_area_state)
        current_global_entities = copy.deepcopy(
            self.persistence_runtime.save_data.current_global_entities
        )
        current_input_targets = copy.deepcopy(
            self.persistence_runtime.save_data.current_input_targets
        )
        current_camera = copy.deepcopy(
            self.persistence_runtime.save_data.current_camera
        )
        self.persistence_runtime.save_data.current_area_state = None
        self.persistence_runtime.save_data.current_global_entities = None
        self.persistence_runtime.save_data.current_input_targets = None
        self.persistence_runtime.save_data.current_camera = None
        target_area_path = self._resolve_saved_area_path()
        self._load_area_runtime(target_area_path)
        if current_area_state is not None:
            apply_persistent_area_state(
                self.area,
                self.world,
                current_area_state,
                project=self.project,
            )
        apply_current_global_state(
            self.area,
            self.world,
            current_global_entities,
            project=self.project,
        )
        self._apply_saved_input_targets(current_input_targets)
        self._apply_saved_camera_state(current_camera)
        self.persistence_runtime.refresh_live_travelers(
            self.area,
            self.world,
            include_transient=False,
        )

    def _resolve_saved_area_path(self) -> Path:
        """Resolve the saved session's current area reference, falling back safely."""
        current_area_path = str(self.persistence_runtime.save_data.current_area).strip()
        if current_area_path:
            return self._resolve_area_path(current_area_path)

        startup_area = self.project.startup_area
        if startup_area:
            return self._resolve_area_path(startup_area)
        return self.area_path.resolve()

    def _apply_saved_input_targets(self, saved_input_targets: dict[str, str] | None) -> None:
        """Restore the saved logical-input routing after the current room is rebuilt."""
        if saved_input_targets:
            self.world.set_input_targets(saved_input_targets, replace=True)

    def _apply_saved_camera_state(self, saved_camera_state: dict[str, object] | None) -> None:
        """Restore the saved camera state after the current room is rebuilt."""
        if saved_camera_state is None or self.camera is None:
            return
        self.camera.apply_state_dict(saved_camera_state, self.world)
