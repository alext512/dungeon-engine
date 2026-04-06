"""Area-loading, transition, and reset helpers for the play runtime."""

from __future__ import annotations

import copy
from pathlib import Path

from dungeon_engine.commands.runner import AreaTransitionRequest, execute_registered_command
from dungeon_engine.world.loader import instantiate_entity, load_area, load_area_from_data
from dungeon_engine.world.persistence import (
    PersistenceRuntime,
    ResetRequest,
    apply_area_travelers,
    apply_persistent_global_state,
    get_persistent_area_state,
    select_entity_ids_by_tags,
)
from dungeon_engine.world.serializer import serialize_area


class GameAreaRuntimeMixin:
    """Provide area loading, transition, and reset helpers for ``Game``."""

    def request_area_change(self, request: AreaTransitionRequest) -> None:
        """Queue a transition into another authored area by area id."""
        self._pending_area_change_request = copy.deepcopy(request)
        self._pending_new_game_request = None
        self._pending_load_save_path = None

    def request_new_game(self, request: AreaTransitionRequest) -> None:
        """Queue a fresh session reset and transition into another authored area."""
        self._pending_new_game_request = copy.deepcopy(request)
        self._pending_area_change_request = None
        self._pending_load_save_path = None

    def _load_area_runtime(
        self,
        area_path: Path | str,
        *,
        transferred_entities: list | None = None,
        restored_input_targets: dict[str, str] | None = None,
        transition_request: AreaTransitionRequest | None = None,
    ) -> None:
        """Load one authored area plus any persistent overrides and rebuild runtime systems."""
        resolved_area_path = self._resolve_area_path(area_path)
        document_area, document_world = load_area(
            resolved_area_path,
            asset_manager=self.asset_manager,
            project=self.project,
        )
        document_data = serialize_area(document_area, document_world, project=self.project)
        play_document_data = copy.deepcopy(document_data)
        play_authored_area, play_authored_world = load_area_from_data(
            copy.deepcopy(document_data),
            source_name=str(resolved_area_path),
            asset_manager=self.asset_manager,
            project=self.project,
        )
        self._install_project_global_entities(play_authored_world, play_authored_area.tile_size)
        self._apply_reentry_resets_for_area(play_authored_area.area_id, play_authored_world)
        area, world = load_area_from_data(
            copy.deepcopy(document_data),
            source_name=str(resolved_area_path),
            asset_manager=self.asset_manager,
            persistent_area_state=get_persistent_area_state(
                self.persistence_runtime.save_data,
                play_authored_area.area_id,
            ),
            project=self.project,
        )
        self._install_project_global_entities(world, area.tile_size)
        apply_persistent_global_state(
            area,
            world,
            self.persistence_runtime.save_data,
            project=self.project,
        )
        transferred_entity_ids = {
            str(entity.entity_id)
            for entity in (transferred_entities or [])
        }
        apply_area_travelers(
            area,
            world,
            self.persistence_runtime.save_data,
            project=self.project,
            skip_entity_ids=transferred_entity_ids,
        )
        self._install_transferred_entities(
            area,
            world,
            transferred_entities or [],
            entry_id=None if transition_request is None else transition_request.entry_id,
            destination_entity_id=(
                None if transition_request is None else transition_request.destination_entity_id
            ),
        )

        self.area_path = resolved_area_path
        self.play_document_data = play_document_data
        self.play_authored_area = play_authored_area
        self.play_authored_world = play_authored_world
        self.area = area
        self.world = world
        self.persistence_runtime.bind_area(
            self.play_authored_area.area_id,
            authored_world=self.play_authored_world,
        )
        self._install_play_runtime()
        self._apply_area_camera_defaults()
        self.persistence_runtime.refresh_live_travelers(
            self.area,
            self.world,
            include_transient=False,
            force_entity_ids=transferred_entity_ids,
        )
        if restored_input_targets:
            self.world.set_input_targets(restored_input_targets, replace=False)
        self._apply_transition_camera_follow(
            None if transition_request is None else transition_request.camera_follow
        )
        self._queue_area_enter_commands()

    def _install_project_global_entities(self, world, tile_size: int) -> None:
        """Instantiate project-authored global entities into the current runtime world."""
        for index, entity_data in enumerate(self.project.global_entities):
            global_entity = instantiate_entity(
                {
                    **copy.deepcopy(entity_data),
                    "scope": "global",
                },
                tile_size,
                project=self.project,
                source_name=f"project global_entities[{index}]",
            )
            existing_entity = world.get_entity(global_entity.entity_id)
            if existing_entity is not None:
                raise ValueError(
                    f"project global_entities[{index}] entity id '{global_entity.entity_id}' "
                    f"conflicts with existing {existing_entity.scope} entity '{existing_entity.entity_id}'."
                )
            world.add_entity(global_entity)

    def _resolve_area_path(self, area_path: Path | str) -> Path:
        """Resolve an area reference (ID or already-resolved path)."""
        if isinstance(area_path, str):
            reference = area_path.strip()
            resolved = self.project.resolve_area_reference(reference)
            if resolved is not None:
                return resolved
            raise FileNotFoundError(
                f"Cannot resolve authored area id '{reference}' in project '{self.project.project_root}'."
            )

        raw_path = Path(area_path)
        candidate_inputs = [raw_path]
        if raw_path.suffix.lower() != ".json":
            candidate_inputs.append(raw_path.with_suffix(".json"))

        candidates: list[Path] = []
        seen: set[Path] = set()

        def _record(candidate: Path) -> None:
            resolved_candidate = candidate.resolve()
            if resolved_candidate in seen:
                return
            seen.add(resolved_candidate)
            candidates.append(candidate)

        for candidate_input in candidate_inputs:
            if candidate_input.is_absolute():
                _record(candidate_input)
                continue
            _record(self.area_path.parent / candidate_input)

        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()

        searched_paths = ", ".join(str(candidate) for candidate in candidates)
        raise FileNotFoundError(
            f"Cannot resolve area reference '{area_path}'. "
            f"Searched: {searched_paths or '<none>'}."
        )

    def _queue_area_enter_commands(self) -> None:
        """Queue area-authored enter commands so they run on the next simulation tick."""
        if self.command_runner is None or not self.area.enter_commands:
            return
        self.command_runner.enqueue(
            "run_commands",
            commands=copy.deepcopy(self.area.enter_commands),
        )

    def _queue_occupancy_transition_hooks(
        self,
        instigator,
        previous_cell: tuple[int, int] | None,
        next_cell: tuple[int, int] | None,
    ) -> None:
        """Queue stationary-entity occupancy hooks for one logical tile transition."""
        if self.command_runner is None or previous_cell == next_cell:
            return

        runtime_params: dict[str, int] = {}
        if previous_cell is not None:
            runtime_params["from_x"] = int(previous_cell[0])
            runtime_params["from_y"] = int(previous_cell[1])
        if next_cell is not None:
            runtime_params["to_x"] = int(next_cell[0])
            runtime_params["to_y"] = int(next_cell[1])

        def _spawn_hook(receiver, command_id: str) -> None:
            handle = execute_registered_command(
                self.command_registry,
                self.command_runner.context,
                "run_entity_command",
                {
                    "entity_id": receiver.entity_id,
                    "command_id": command_id,
                    "entity_refs": {"instigator": instigator.entity_id},
                    "refs_mode": "merge",
                    **runtime_params,
                },
            )
            self.command_runner.spawn_root_handle(handle)

        if previous_cell is not None:
            for receiver in self.world.get_entities_at(
                previous_cell[0],
                previous_cell[1],
                exclude_entity_id=instigator.entity_id,
                include_hidden=True,
            ):
                _spawn_hook(receiver, "on_occupant_leave")

        if next_cell is not None:
            for receiver in self.world.get_entities_at(
                next_cell[0],
                next_cell[1],
                exclude_entity_id=instigator.entity_id,
                include_hidden=True,
            ):
                _spawn_hook(receiver, "on_occupant_enter")

    def _apply_pending_reset_if_idle(self) -> None:
        """Apply queued immediate reset requests once the command lane is idle."""
        if self.command_runner is None or self._has_blocking_runtime_work():
            return

        request = self.persistence_runtime.consume_immediate_reset()
        if request is None:
            return

        if request.kind == "persistent":
            self.persistence_runtime.clear_persistent_area_state(
                self.play_authored_area.area_id,
                self.play_authored_world,
                include_tags=request.include_tags,
                exclude_tags=request.exclude_tags,
            )

        self._apply_runtime_reset(request)

    def _apply_pending_load_if_idle(self) -> None:
        """Apply a queued save-slot load once the command lane is idle."""
        if self.command_runner is None or self._has_blocking_runtime_work():
            return
        if self._pending_load_save_path is None:
            return

        load_path = self._pending_load_save_path
        self._pending_load_save_path = None
        self._accumulated_time = 0.0
        self._load_save_slot(load_path)

    def _apply_pending_new_game_if_idle(self) -> None:
        """Apply a queued new-game request once the command lane is idle."""
        if self.command_runner is None or self._has_blocking_runtime_work():
            return
        if self._pending_new_game_request is None:
            return

        request = self._pending_new_game_request
        self._pending_new_game_request = None
        self._accumulated_time = 0.0
        self.persistence_runtime = PersistenceRuntime(project=self.project)
        self._apply_area_transition_request(request)

    def _apply_pending_area_change_if_idle(self) -> None:
        """Apply a queued area transition once the main command lane is idle."""
        if self.command_runner is None or self._has_blocking_runtime_work():
            return
        if self._pending_area_change_request is None:
            return

        request = self._pending_area_change_request
        self._pending_area_change_request = None
        self._accumulated_time = 0.0
        self._apply_area_transition_request(request)

    def _apply_reentry_resets_for_area(self, area_id: str, authored_world) -> None:
        """Apply scheduled on-reentry persistent resets before constructing an area runtime."""
        for request in self.persistence_runtime.consume_reentry_resets(area_id):
            if request.kind != "persistent":
                continue
            self.persistence_runtime.clear_persistent_area_state(
                area_id,
                authored_world,
                include_tags=request.include_tags,
                exclude_tags=request.exclude_tags,
            )

    def _apply_runtime_reset(self, request: ResetRequest) -> None:
        """Reset the whole room or matching entities against authored+persistent state."""
        selected_ids = set(request.entity_ids)
        if not selected_ids:
            selected_ids = set(
                select_entity_ids_by_tags(
                    self.play_authored_world,
                    include_tags=request.include_tags,
                    exclude_tags=request.exclude_tags,
                )
            )
        if not selected_ids and not request.include_tags and not request.exclude_tags:
            self._rebuild_play_world()
            return
        if not selected_ids:
            return

        reference_area, reference_world = self._build_current_play_reference()
        apply_area_travelers(
            reference_area,
            reference_world,
            self.persistence_runtime.save_data,
            project=self.project,
        )
        for entity_id in selected_ids:
            current_entity = self.world.get_entity(entity_id)
            reference_entity = reference_world.get_entity(entity_id)
            if reference_entity is None:
                if current_entity is not None:
                    self.world.remove_entity(entity_id)
                continue
            self.world.replace_entity(copy.deepcopy(reference_entity))

    def _build_current_play_reference(self):
        """Build a fresh play world from authored data plus current persistent overrides."""
        if self.play_document_data is None:
            raise RuntimeError("Game runtime is missing the current play document.")
        area, world = load_area_from_data(
            copy.deepcopy(self.play_document_data),
            source_name=str(self.area_path),
            asset_manager=self.asset_manager,
            persistent_area_state=get_persistent_area_state(
                self.persistence_runtime.save_data,
                self.play_authored_area.area_id,
            ),
            project=self.project,
        )
        self._install_project_global_entities(world, area.tile_size)
        apply_persistent_global_state(
            area,
            world,
            self.persistence_runtime.save_data,
            project=self.project,
        )
        return area, world

    def _apply_area_transition_request(self, request: AreaTransitionRequest) -> None:
        """Apply one authored area transition, optionally carrying runtime entities with it."""
        resolved_area_path = self._resolve_area_path(request.area_id)
        self.persistence_runtime.refresh_live_travelers(
            self.area,
            self.world,
            include_transient=False,
        )
        transferred_entities = self._capture_transition_entities(request)
        for entity in transferred_entities:
            self.persistence_runtime.prepare_traveler_for_area(
                entity,
                destination_area_id=request.area_id,
                tile_size=self.area.tile_size,
            )
        restored_input_targets = self._capture_transition_input_targets(transferred_entities)
        self._load_area_runtime(
            resolved_area_path,
            transferred_entities=transferred_entities,
            restored_input_targets=restored_input_targets,
            transition_request=request,
        )

    def _capture_transition_entities(self, request: AreaTransitionRequest) -> list:
        """Return detached entity copies that should move into the next area."""
        transferred_entities: list = []
        for entity_id in request.transfer_entity_ids:
            entity = self.world.get_entity(entity_id)
            if entity is None:
                raise KeyError(
                    f"Cannot transfer missing entity '{entity_id}' during area change to '{request.area_id}'."
                )
            if entity.scope != "area":
                raise ValueError(
                    f"Cannot transfer entity '{entity_id}' because only area-scoped entities can change areas."
                )
            transferred_entity = copy.deepcopy(entity)
            transferred_entity.movement_state.active = False
            for visual in transferred_entity.visuals:
                visual.animation_playback.active = False
            transferred_entities.append(transferred_entity)
        return transferred_entities

    def _capture_transition_input_targets(self, transferred_entities: list) -> dict[str, str]:
        """Carry routed actions that currently target transferred entities into the next area."""
        transferred_ids = {
            entity.entity_id
            for entity in transferred_entities
        }
        if not transferred_ids:
            return {}
        preserved_targets: dict[str, str] = {}
        for action, target_id in self.world.input_targets.items():
            if target_id in transferred_ids:
                preserved_targets[action] = str(target_id)
        return preserved_targets

    def _install_transferred_entities(
        self,
        area,
        world,
        transferred_entities: list,
        *,
        entry_id: str | None,
        destination_entity_id: str | None = None,
    ) -> None:
        """Place transferred entities into the loaded destination area before runtime rebuild."""
        if not transferred_entities:
            return
        entry_point = None
        destination_entity = None
        if destination_entity_id:
            destination_entity = world.get_entity(destination_entity_id)
            if destination_entity is None:
                raise KeyError(
                    f"Area '{area.area_id}' does not define destination entity '{destination_entity_id}'."
                )
        if entry_id:
            entry_point = area.entry_points.get(entry_id)
            if entry_point is None:
                raise KeyError(
                    f"Area '{area.area_id}' does not define entry point '{entry_id}'."
                )

        for entity in transferred_entities:
            self._place_transferred_entity(
                area,
                entity,
                entry_point=entry_point,
                destination_entity=destination_entity,
            )
            world.add_entity(entity)

    def _place_transferred_entity(self, area, entity, *, entry_point, destination_entity) -> None:
        """Move one transferred entity onto the destination entry marker when provided."""
        if entity.space != "world":
            return
        if destination_entity is not None:
            if destination_entity.space != "world":
                raise ValueError(
                    f"Destination entity '{destination_entity.entity_id}' must be world-space."
                )
            entity.grid_x = int(destination_entity.grid_x)
            entity.grid_y = int(destination_entity.grid_y)
            if destination_entity.facing:
                entity.set_facing_value(str(destination_entity.facing))
            entity.pixel_x = float(destination_entity.pixel_x)
            entity.pixel_y = float(destination_entity.pixel_y)
            return
        if entry_point is None:
            entity.sync_pixel_position(area.tile_size)
            return
        entity.grid_x = int(entry_point.grid_x)
        entity.grid_y = int(entry_point.grid_y)
        if entry_point.facing is not None:
            entity.set_facing_value(str(entry_point.facing))
        entity.pixel_x = (
            float(entry_point.pixel_x)
            if entry_point.pixel_x is not None
            else float(entity.grid_x * area.tile_size)
        )
        entity.pixel_y = (
            float(entry_point.pixel_y)
            if entry_point.pixel_y is not None
            else float(entity.grid_y * area.tile_size)
        )

    def _apply_transition_camera_follow(self, camera_follow) -> None:
        """Apply any authored camera-follow request after a transition rebuilds runtime state."""
        if self.camera is None or camera_follow is None:
            return
        if camera_follow.mode == "entity" and camera_follow.entity_id:
            if self.world.get_entity(camera_follow.entity_id) is None:
                raise KeyError(
                    f"Cannot follow missing transition camera entity '{camera_follow.entity_id}'."
                )
            self.camera.follow_entity(
                camera_follow.entity_id,
                offset_x=float(camera_follow.offset_x),
                offset_y=float(camera_follow.offset_y),
            )
        elif camera_follow.mode == "input_target" and camera_follow.action:
            self.camera.follow_input_target(
                camera_follow.action,
                offset_x=float(camera_follow.offset_x),
                offset_y=float(camera_follow.offset_y),
            )
        elif camera_follow.mode == "none":
            self.camera.clear_follow()
        self.camera.update(self.world, advance_tick=False)

    def _rebuild_play_world(self) -> None:
        """Rebuild the current play world from authored data plus persistent overrides."""
        self.persistence_runtime.refresh_live_travelers(
            self.area,
            self.world,
            include_transient=False,
        )
        self.area, self.world = self._build_current_play_reference()
        apply_area_travelers(
            self.area,
            self.world,
            self.persistence_runtime.save_data,
            project=self.project,
        )
        self._install_play_runtime()

    def _apply_area_camera_defaults(self) -> None:
        """Apply authored area camera defaults when the room has any."""
        if self.camera is None or not self.area.camera_defaults:
            return
        self.camera.apply_state_dict(self._build_area_camera_state(), self.world)

    def _build_area_camera_state(self) -> dict[str, object]:
        """Translate one area's authored camera defaults into runtime camera state data."""
        return copy.deepcopy(self.area.camera_defaults)
