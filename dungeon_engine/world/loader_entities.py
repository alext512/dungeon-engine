"""Entity and template loading helpers shared by world loading and startup validation."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from dungeon_engine.authored_command_validation import (
    RESERVED_ENTITY_IDS,
    validate_authored_command_tree,
)
from dungeon_engine.inventory import clone_inventory_state
from dungeon_engine.items import load_item_definition
from dungeon_engine.json_io import JsonDataDecodeError, load_json_data
from dungeon_engine.logging_utils import get_logger
from dungeon_engine.project_context import ProjectContext
from dungeon_engine.world.entity import (
    Entity,
    EntityCommandDefinition,
    EntityPersistencePolicy,
    EntityVisual,
    InventoryStack,
    InventoryState,
)

logger = get_logger(__name__)

_TEMPLATE_CACHE: dict[tuple[Path, str], dict[str, Any]] = {}


class EntityTemplateValidationError(ValueError):
    """Raised when entity template files fail startup validation."""

    def __init__(self, project_root: Path, issues: list[str]) -> None:
        self.project_root = project_root
        self.issues = list(issues)
        super().__init__(
            f"Entity template validation failed for '{project_root}' with {len(self.issues)} issue(s)."
        )

    def format_user_message(self, *, max_issues: int = 8) -> str:
        """Return a short user-facing validation summary."""
        shown_issues = self.issues[:max_issues]
        lines = [
            f"Entity template validation failed with {len(self.issues)} issue(s).",
            "See logs/error.log for full details.",
            "",
            "First issues:",
        ]
        lines.extend(f"- {issue}" for issue in shown_issues)
        hidden_count = len(self.issues) - len(shown_issues)
        if hidden_count > 0:
            lines.append(f"- ...and {hidden_count} more")
        return "\n".join(lines)

def instantiate_entity(
    entity_instance: dict[str, Any],
    tile_size: int,
    *,
    project: ProjectContext,
    source_name: str = "<entity>",
    allow_missing_inventory_items: bool = False,
) -> Entity:
    """Create a runtime entity from an instance definition or template reference."""
    if not isinstance(entity_instance, dict):
        raise ValueError(f"{source_name} must be a JSON object.")

    template_id = _normalize_optional_id(entity_instance.get("template"))
    entity_data = _resolve_entity_instance(
        entity_instance,
        project=project,
        source_name=source_name,
    )
    entity_id = _require_non_empty_string(entity_data, "id", source_name=source_name)
    if entity_id in RESERVED_ENTITY_IDS:
        reserved_names = ", ".join(sorted(RESERVED_ENTITY_IDS))
        raise ValueError(
            f"{source_name} field 'id' must not use reserved runtime entity reference "
            f"'{entity_id}' ({reserved_names})."
        )
    kind = _require_non_empty_string(entity_data, "kind", source_name=source_name)
    space = _parse_entity_space(entity_data, source_name=source_name)
    scope = _parse_entity_scope(entity_data, source_name=source_name)
    if space == "world":
        grid_x = _coerce_required_int(entity_data, "grid_x", source_name=source_name)
        grid_y = _coerce_required_int(entity_data, "grid_y", source_name=source_name)
        default_pixel_x = float(grid_x * tile_size)
        default_pixel_y = float(grid_y * tile_size)
    else:
        if "grid_x" in entity_data or "grid_y" in entity_data:
            raise ValueError(
                f"{source_name} screen-space entities must not declare 'grid_x'/'grid_y'; use 'pixel_x'/'pixel_y' or visual offsets."
            )
        grid_x = 0
        grid_y = 0
        default_pixel_x = 0.0
        default_pixel_y = 0.0

    variables = _parse_entity_variables(entity_data, source_name=source_name)
    persistence = _parse_entity_persistence(entity_data, source_name=source_name)
    visuals = _parse_entity_visuals(entity_data, tile_size=tile_size, source_name=source_name)
    entity_commands = _parse_entity_commands(entity_data)
    facing = _parse_entity_facing(entity_data, source_name=source_name)
    solid = _parse_entity_solid(entity_data)
    pushable = _parse_entity_pushable(entity_data)
    weight = _parse_entity_weight(entity_data, source_name=source_name)
    push_strength = _parse_entity_push_strength(entity_data, source_name=source_name)
    collision_push_strength = _parse_entity_collision_push_strength(
        entity_data,
        source_name=source_name,
    )
    interactable = _parse_entity_interactable(entity_data)
    inventory = _parse_entity_inventory(
        entity_data,
        project=project,
        source_name=source_name,
        allow_missing_item_definitions=allow_missing_inventory_items,
    )
    entity = Entity(
        entity_id=entity_id,
        kind=kind,
        grid_x=grid_x,
        grid_y=grid_y,
        pixel_x=float(entity_data.get("pixel_x", default_pixel_x)),
        pixel_y=float(entity_data.get("pixel_y", default_pixel_y)),
        space=space,
        scope=scope,
        present=bool(entity_data.get("present", True)),
        visible=bool(entity_data.get("visible", True)),
        facing=facing,
        solid=solid,
        pushable=pushable,
        weight=weight,
        push_strength=push_strength,
        collision_push_strength=collision_push_strength,
        interactable=interactable,
        interaction_priority=int(entity_data.get("interaction_priority", 0)),
        entity_commands_enabled=bool(entity_data.get("entity_commands_enabled", True)),
        render_order=_parse_entity_render_order(entity_data, space=space),
        y_sort=_parse_entity_y_sort(entity_data, space=space),
        sort_y_offset=float(entity_data.get("sort_y_offset", 0.0)),
        stack_order=int(entity_data.get("stack_order", 0)),
        color=_parse_color(entity_data.get("color")),
        template_id=template_id,
        template_parameters=copy.deepcopy(entity_instance.get("parameters", {})),
        tags=_coerce_string_list(entity_data.get("tags", []), field_name="tags", source_name=source_name),
        inventory=clone_inventory_state(inventory),
        visuals=visuals,
        entity_commands=entity_commands,
        variables=variables,
        input_map=_parse_input_map(entity_data.get("input_map")),
        persistence=persistence,
    )
    return entity


def _parse_entity_variables(entity_data: dict[str, Any], *, source_name: str) -> dict[str, Any]:
    """Parse one entity's variables object."""
    raw_variables = entity_data.get("variables", {})
    if raw_variables is None:
        return {}
    if not isinstance(raw_variables, dict):
        raise ValueError(f"{source_name} field 'variables' must be a JSON object.")
    return copy.deepcopy(raw_variables)


def _parse_entity_persistence(
    entity_data: dict[str, Any],
    *,
    source_name: str,
) -> EntityPersistencePolicy:
    """Parse one entity's optional persistence policy."""
    raw_persistence = entity_data.get("persistence")
    if raw_persistence is None:
        return EntityPersistencePolicy()
    if not isinstance(raw_persistence, dict):
        raise ValueError(f"{source_name} field 'persistence' must be a JSON object.")

    raw_entity_state = raw_persistence.get("entity_state", False)
    if not isinstance(raw_entity_state, bool):
        raise ValueError(f"{source_name} field 'persistence.entity_state' must be true or false.")

    raw_variables = raw_persistence.get("variables", {})
    if raw_variables is None:
        raw_variables = {}
    if not isinstance(raw_variables, dict):
        raise ValueError(f"{source_name} field 'persistence.variables' must be a JSON object.")

    variables: dict[str, bool] = {}
    for name, raw_value in raw_variables.items():
        resolved_name = str(name).strip()
        if not resolved_name:
            raise ValueError(
                f"{source_name} field 'persistence.variables' must not use blank variable names."
            )
        if not isinstance(raw_value, bool):
            raise ValueError(
                f"{source_name} field 'persistence.variables.{resolved_name}' must be true or false."
            )
        variables[resolved_name] = raw_value

    return EntityPersistencePolicy(
        entity_state=raw_entity_state,
        variables=variables,
    )


def _parse_entity_inventory(
    entity_data: dict[str, Any],
    *,
    project: ProjectContext,
    source_name: str,
    allow_missing_item_definitions: bool,
) -> InventoryState | None:
    """Parse one entity's optional inventory payload."""
    raw_inventory = entity_data.get("inventory")
    if raw_inventory is None:
        return None
    if not isinstance(raw_inventory, dict):
        raise ValueError(f"{source_name} field 'inventory' must be a JSON object.")

    if "max_stacks" not in raw_inventory:
        raise ValueError(f"{source_name} field 'inventory' must define 'max_stacks'.")
    max_stacks = int(raw_inventory.get("max_stacks", 0))
    if max_stacks < 0:
        raise ValueError(f"{source_name} field 'inventory.max_stacks' must be zero or positive.")

    raw_stacks = raw_inventory.get("stacks", [])
    if raw_stacks is None:
        raw_stacks = []
    if not isinstance(raw_stacks, list):
        raise ValueError(f"{source_name} field 'inventory.stacks' must be a JSON array.")

    stacks: list[InventoryStack] = []
    item_max_stack_cache: dict[str, int | None] = {}
    for index, raw_stack in enumerate(raw_stacks):
        if not isinstance(raw_stack, dict):
            raise ValueError(f"{source_name} inventory.stacks[{index}] must be a JSON object.")
        item_id = _require_non_empty_string(
            raw_stack,
            "item_id",
            source_name=f"{source_name} inventory.stacks[{index}]",
        )
        quantity = _coerce_required_int(
            raw_stack,
            "quantity",
            source_name=f"{source_name} inventory.stacks[{index}]",
        )
        if quantity <= 0:
            raise ValueError(
                f"{source_name} inventory.stacks[{index}] field 'quantity' must be positive."
            )

        item_max_stack = item_max_stack_cache.get(item_id)
        if item_id not in item_max_stack_cache:
            try:
                item_definition = load_item_definition(project, item_id)
            except FileNotFoundError:
                if allow_missing_item_definitions:
                    logger.warning(
                        "%s inventory.stacks[%d] preserves unresolved item '%s' because its definition is missing.",
                        source_name,
                        index,
                        item_id,
                    )
                    item_max_stack = None
                else:
                    raise ValueError(
                        f"{source_name} inventory.stacks[{index}] references unknown item '{item_id}'."
                    ) from None
            else:
                item_max_stack = int(item_definition.max_stack)
            item_max_stack_cache[item_id] = item_max_stack

        if item_max_stack is not None and quantity > item_max_stack:
            raise ValueError(
                f"{source_name} inventory.stacks[{index}] quantity {quantity} exceeds item "
                f"'{item_id}' max_stack {item_max_stack}."
            )
        stacks.append(
            InventoryStack(
                item_id=item_id,
                quantity=quantity,
            )
        )

    if len(stacks) > max_stacks:
        raise ValueError(
            f"{source_name} inventory uses {len(stacks)} stack(s) but max_stacks is {max_stacks}."
        )

    return InventoryState(
        max_stacks=max_stacks,
        stacks=stacks,
    )


def _parse_entity_facing(
    entity_data: dict[str, Any],
    *,
    source_name: str,
) -> str:
    """Parse one entity's top-level facing field."""
    raw_facing = entity_data.get("facing", "down")
    facing = str(raw_facing).strip().lower()
    if facing not in {"up", "down", "left", "right"}:
        raise ValueError(
            f"{source_name} field 'facing' must be 'up', 'down', 'left', or 'right'."
        )
    return facing


def _parse_entity_solid(
    entity_data: dict[str, Any],
) -> bool:
    """Parse one entity's top-level solid flag."""
    return bool(entity_data.get("solid", False))


def _parse_entity_pushable(
    entity_data: dict[str, Any],
) -> bool:
    """Parse one entity's top-level pushable flag."""
    return bool(entity_data.get("pushable", False))


def _parse_entity_weight(
    entity_data: dict[str, Any],
    *,
    source_name: str,
) -> int:
    """Parse one entity's authored weight."""
    weight = int(entity_data.get("weight", 1))
    if weight <= 0:
        raise ValueError(f"{source_name} field 'weight' must be positive.")
    return weight


def _parse_entity_push_strength(
    entity_data: dict[str, Any],
    *,
    source_name: str,
) -> int:
    """Parse one entity's authored push strength."""
    push_strength = int(entity_data.get("push_strength", 0))
    if push_strength < 0:
        raise ValueError(f"{source_name} field 'push_strength' must be zero or positive.")
    return push_strength


def _parse_entity_collision_push_strength(
    entity_data: dict[str, Any],
    *,
    source_name: str,
) -> int:
    """Parse one entity's authored collision push strength."""
    collision_push_strength = int(entity_data.get("collision_push_strength", 0))
    if collision_push_strength < 0:
        raise ValueError(
            f"{source_name} field 'collision_push_strength' must be zero or positive."
        )
    return collision_push_strength


def _parse_entity_interactable(
    entity_data: dict[str, Any],
) -> bool:
    """Parse one entity's top-level interactable flag."""
    return bool(entity_data.get("interactable", False))


def _parse_entity_space(entity_data: dict[str, Any], *, source_name: str) -> str:
    """Parse one entity's spatial domain."""
    space = str(entity_data.get("space", "world")).strip().lower()
    if space not in {"world", "screen"}:
        raise ValueError(f"{source_name} field 'space' must be 'world' or 'screen'.")
    return space


def _parse_entity_scope(entity_data: dict[str, Any], *, source_name: str) -> str:
    """Parse one entity's lifetime scope."""
    scope = str(entity_data.get("scope", "area")).strip().lower()
    if scope not in {"area", "global"}:
        raise ValueError(f"{source_name} field 'scope' must be 'area' or 'global'.")
    return scope


def _parse_entity_render_order(entity_data: dict[str, Any], *, space: str) -> int:
    """Parse the unified entity render band."""
    if "render_order" in entity_data:
        return int(entity_data.get("render_order", 0))
    return 10 if space == "world" else 0


def _parse_entity_y_sort(entity_data: dict[str, Any], *, space: str) -> bool:
    """Parse whether one entity participates in vertical interleaving."""
    if "y_sort" in entity_data:
        return bool(entity_data.get("y_sort", False))
    return space == "world"


def _parse_entity_visuals(
    entity_data: dict[str, Any],
    *,
    tile_size: int,
    source_name: str,
) -> list[EntityVisual]:
    """Parse and validate one entity's visuals list."""
    if "sprite" in entity_data:
        raise ValueError(
            f"{source_name} must not use 'sprite'; entities now define a 'visuals' array."
        )

    raw_visuals = entity_data.get("visuals", [])
    if raw_visuals is None:
        raw_visuals = []
    if not isinstance(raw_visuals, list):
        raise ValueError(f"{source_name} field 'visuals' must be a JSON array.")

    visuals: list[EntityVisual] = []
    seen_visual_ids: set[str] = set()
    for index, raw_visual in enumerate(raw_visuals):
        if not isinstance(raw_visual, dict):
            raise ValueError(f"{source_name} visuals[{index}] must be a JSON object.")
        visual_id = _require_non_empty_string(
            raw_visual,
            "id",
            source_name=f"{source_name} visuals[{index}]",
        )
        if visual_id in seen_visual_ids:
            raise ValueError(f"{source_name} uses duplicate visual id '{visual_id}'.")
        seen_visual_ids.add(visual_id)

        raw_frames = raw_visual.get("frames", [0])
        if not isinstance(raw_frames, list):
            raise ValueError(f"{source_name} visuals[{index}] field 'frames' must be a JSON array.")
        frames = [int(frame) for frame in raw_frames]
        if not frames:
            raise ValueError(f"{source_name} visuals[{index}] field 'frames' must not be empty.")

        frame_width = int(raw_visual.get("frame_width", tile_size))
        frame_height = int(raw_visual.get("frame_height", tile_size))
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError(f"{source_name} visuals[{index}] frame dimensions must be positive.")

        tint = _parse_color(raw_visual.get("tint"))
        visuals.append(
            EntityVisual(
                visual_id=visual_id,
                path=_require_non_empty_string(
                    raw_visual,
                    "path",
                    source_name=f"{source_name} visuals[{index}]",
                ),
                frame_width=frame_width,
                frame_height=frame_height,
                frames=frames,
                animation_fps=float(raw_visual.get("animation_fps", 0.0)),
                animate_when_moving=bool(raw_visual.get("animate_when_moving", False)),
                current_frame=int(frames[0]),
                flip_x=bool(raw_visual.get("flip_x", False)),
                visible=bool(raw_visual.get("visible", True)),
                tint=tint,
                offset_x=float(raw_visual.get("offset_x", 0.0)),
                offset_y=float(raw_visual.get("offset_y", 0.0)),
                draw_order=int(raw_visual.get("draw_order", index)),
            )
        )

    return visuals


def list_entity_template_ids(project: ProjectContext) -> list[str]:
    """Return all available entity template ids in a stable order."""
    return project.list_entity_template_ids()


def load_entity_template(template_id: str, *, project: ProjectContext) -> dict[str, Any]:
    """Load and cache a reusable entity template by its file name."""
    return _load_entity_template(template_id, project=project)


def _resolve_entity_instance(
    instance_data: dict[str, Any],
    *,
    project: ProjectContext,
    source_name: str,
) -> dict[str, Any]:
    """Merge a reusable template with a level-specific instance definition."""
    template_id = _normalize_optional_id(instance_data.get("template"))
    if template_id is None:
        resolved = copy.deepcopy(instance_data)
    else:
        template_data = _load_entity_template(template_id, project=project)
        resolved = _deep_merge(template_data, instance_data)

    parameters = resolved.pop("parameters", {})
    if parameters is None:
        parameters = {}
    if not isinstance(parameters, dict):
        raise ValueError(f"{source_name} field 'parameters' must be a JSON object.")
    resolved.pop("template", None)
    substituted = _substitute_parameters(resolved, dict(parameters))
    if not isinstance(substituted, dict):
        raise ValueError(f"{source_name} must resolve to a JSON object after template expansion.")
    return substituted


def _load_entity_template(template_id: str, *, project: ProjectContext) -> dict[str, Any]:
    """Load and cache a reusable entity template by its path-derived id.

    Template ids support subdirectories (e.g. ``"entity_templates/npcs/village_guard"``).
    """
    normalized_id = str(template_id).replace("\\", "/").strip()
    cache_key = (project.project_root.resolve(), normalized_id)
    cached = _TEMPLATE_CACHE.get(cache_key)
    if cached is not None:
        return copy.deepcopy(cached)

    template_path = project.find_entity_template(normalized_id)
    if template_path is None or not template_path.exists():
        raise FileNotFoundError(f"Missing entity template '{normalized_id}'.")

    template_data = load_json_data(template_path)
    _TEMPLATE_CACHE[cache_key] = template_data
    return copy.deepcopy(template_data)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge dictionaries while letting instance data win."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def extract_template_parameter_names(
    template_id: str,
    *,
    project: ProjectContext,
) -> list[str]:
    """Return the parameter placeholder names used by a template.

    Scans the template JSON for ``$name`` and ``${name}`` tokens and returns
    a sorted list of unique parameter names. Useful for authoring tools
    property inspector with empty values.
    """
    try:
        data = _load_entity_template(template_id, project=project)
    except FileNotFoundError:
        return []
    found: set[str] = set()
    _collect_parameter_tokens(data, found)
    return sorted(found)


def _collect_parameter_tokens(value: Any, found: set[str]) -> None:
    """Recursively find ``$name`` / ``${name}`` tokens in a data tree."""
    if isinstance(value, dict):
        for item in value.values():
            _collect_parameter_tokens(item, found)
    elif isinstance(value, list):
        for item in value:
            _collect_parameter_tokens(item, found)
    elif isinstance(value, str):
        if value.startswith("${") and value.endswith("}"):
            found.add(value[2:-1])
        elif value.startswith("$"):
            found.add(value[1:])


def _substitute_parameters(value: Any, parameters: dict[str, Any]) -> Any:
    """Replace '$name' or '${name}' strings with per-instance parameter values."""
    if isinstance(value, dict):
        return {key: _substitute_parameters(item, parameters) for key, item in value.items()}

    if isinstance(value, list):
        return [_substitute_parameters(item, parameters) for item in value]

    if isinstance(value, str):
        token = None
        if value.startswith("${") and value.endswith("}"):
            token = value[2:-1]
        elif value.startswith("$"):
            token = value[1:]

        if token is not None and token in parameters:
            return copy.deepcopy(parameters[token])

    return value


def _parse_color(
    raw_color: list[int] | tuple[int, int, int] | None,
) -> tuple[int, int, int]:
    """Return one RGB color tuple."""
    if raw_color is None:
        return (255, 255, 255)
    return (int(raw_color[0]), int(raw_color[1]), int(raw_color[2]))


def _parse_entity_commands(entity_data: dict[str, Any]) -> dict[str, EntityCommandDefinition]:
    """Parse named entity commands from the authored ``entity_commands`` object."""
    parsed_commands: dict[str, EntityCommandDefinition] = {}

    if "interact_commands" in entity_data:
        raise ValueError(
            "Entity data must not use 'interact_commands'; define an 'entity_commands.interact' entry instead."
        )
    if "events" in entity_data:
        raise ValueError(
            "Entity data must not use 'events'; define named commands under 'entity_commands' instead."
        )

    raw_commands = entity_data.get("entity_commands", {})
    if isinstance(raw_commands, dict):
        for command_id, raw_command in raw_commands.items():
            enabled, commands = _parse_entity_command_definition(
                raw_command,
                source_name="Entity data",
                command_id=str(command_id),
            )
            parsed_commands[str(command_id)] = EntityCommandDefinition(
                enabled=enabled,
                commands=commands,
            )

    return parsed_commands


def _parse_input_map(raw_input_map: Any) -> dict[str, str]:
    """Parse an optional entity-owned logical-input to entity-command map."""
    if not isinstance(raw_input_map, dict):
        return {}
    return {
        str(action): str(command_name)
        for action, command_name in raw_input_map.items()
    }
def validate_project_entity_templates(project: ProjectContext) -> None:
    """Validate entity template files for a project at startup.

    Checks for duplicate IDs, invalid JSON, and basic structure issues.
    """
    known_ids: dict[str, list[Path]] = {}
    for template_path in project.list_entity_template_files():
        template_id = project.entity_template_id(template_path)
        known_ids.setdefault(template_id, []).append(template_path)

    issues: list[str] = []
    for template_id, paths in sorted(known_ids.items()):
        if len(paths) > 1:
            formatted_paths = ", ".join(str(path) for path in paths)
            issues.append(f"Duplicate entity template id '{template_id}' found in: {formatted_paths}")
            continue

        template_path = paths[0]
        try:
            raw = load_json_data(template_path)
            if not isinstance(raw, dict):
                issues.append(f"{template_path}: entity template must be a JSON object.")
                continue
            _validate_entity_template_raw(
                raw,
                source_name=str(template_path),
            )
        except JsonDataDecodeError as exc:
            issues.append(
                f"{template_path}: invalid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})."
            )
        except Exception as exc:
            issues.append(f"{template_path}: {exc}")

    if issues:
        raise EntityTemplateValidationError(project.project_root, issues)


def log_entity_template_validation_error(error: EntityTemplateValidationError) -> None:
    """Write a full entity template validation failure report to the persistent log."""
    logger.error(
        "Entity template validation failed for %s with %d issue(s):\n%s",
        error.project_root,
        len(error.issues),
        "\n".join(f"- {issue}" for issue in error.issues),
    )


def _validate_entity_template_raw(raw_template: dict[str, Any], *, source_name: str) -> None:
    """Reject removed entity-template fields and command shapes before instantiation."""
    if "sprite" in raw_template:
        raise ValueError(
            f"{source_name} must not use 'sprite'; entities now define a 'visuals' array."
        )
    if "interact_commands" in raw_template:
        raise ValueError(
            f"{source_name} must not use 'interact_commands'; define an 'entity_commands.interact' entry instead."
        )
    if "events" in raw_template:
        raise ValueError(
            f"{source_name} must not use 'events'; define named commands under 'entity_commands' instead."
        )

    raw_entity_commands = raw_template.get("entity_commands", {})
    if raw_entity_commands is None:
        return
    if not isinstance(raw_entity_commands, dict):
        raise ValueError(f"{source_name} field 'entity_commands' must be a JSON object.")

    for command_id, raw_command in raw_entity_commands.items():
        _parse_entity_command_definition(
            raw_command,
            source_name=source_name,
            command_id=str(command_id),
        )


def _parse_entity_command_definition(
    raw_command: Any,
    *,
    source_name: str,
    command_id: str,
) -> tuple[bool, list[dict[str, Any]]]:
    """Parse one authored entity-command entry in shorthand or explicit form."""
    if isinstance(raw_command, list):
        validate_authored_command_tree(
            raw_command,
            source_name=source_name,
            location=f"entity_commands.{command_id}",
        )
        return True, copy.deepcopy(raw_command)

    if not isinstance(raw_command, dict):
        raise ValueError(
            f"{source_name} entity command '{command_id}' must be either a JSON array or an object with 'enabled' and 'commands'."
        )
    if "enabled" not in raw_command or "commands" not in raw_command:
        raise ValueError(
            f"{source_name} entity command '{command_id}' object form must define both 'enabled' and 'commands'."
        )

    raw_commands = raw_command.get("commands", [])
    if not isinstance(raw_commands, list):
        raise ValueError(
            f"{source_name} entity command '{command_id}' field 'commands' must be a JSON array."
        )

    validate_authored_command_tree(
        raw_commands,
        source_name=source_name,
        location=f"entity_commands.{command_id}.commands",
    )
    return bool(raw_command.get("enabled", True)), copy.deepcopy(raw_commands)


def _normalize_optional_id(value: Any) -> str | None:
    """Return a stripped optional id string."""
    if value is None:
        return None
    text = str(value).replace("\\", "/").strip()
    return text or None


def _require_non_empty_string(data: dict[str, Any], key: str, *, source_name: str) -> str:
    """Read one required non-empty string field from a mapping."""
    if key not in data:
        raise ValueError(f"{source_name} is missing required field '{key}'.")
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source_name} field '{key}' must be a non-empty string.")
    return value.strip()


def _coerce_int(value: Any, *, field_name: str, source_name: str) -> int:
    """Coerce one integer field with a descriptive error."""
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{source_name} field '{field_name}' must be an integer.") from exc


def _coerce_required_int(data: dict[str, Any], key: str, *, source_name: str) -> int:
    """Read one required integer field from a mapping."""
    if key not in data:
        raise ValueError(f"{source_name} is missing required field '{key}'.")
    return _coerce_int(data[key], field_name=key, source_name=source_name)


def _coerce_string_list(value: Any, *, field_name: str, source_name: str) -> list[str]:
    """Return a list[str] or raise a descriptive validation error."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{source_name} field '{field_name}' must be a JSON array.")
    return [str(item) for item in value]
