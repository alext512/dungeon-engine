"""Entity and template loading helpers shared by world loading and startup validation."""

from __future__ import annotations

import copy
import re
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
    VisualAnimationClip,
)

logger = get_logger(__name__)
_MISSING = object()

_TEMPLATE_CACHE: dict[tuple[Path, str], dict[str, Any]] = {}
_AUTHORED_ENTITY_INDEX_CACHE: dict[
    tuple[Path, tuple[tuple[Path, int | None, int | None], ...]],
    dict[str, list[dict[str, Any]]],
] = {}
_AUTHORED_ENTITY_INDEX_PROJECT_CACHE: dict[int, tuple[ProjectContext, dict[str, list[dict[str, Any]]]]] = {}
_PARAMETER_TOKEN_RE = re.compile(
    r"^\$(?:{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)}|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))$"
)
_PARAMETER_SPEC_TYPES = frozenset(
    {
        "string",
        "text",
        "bool",
        "int",
        "number",
        "enum",
        "array",
        "json",
        "entity_id",
        "entity_command_id",
        "area_id",
        "item_id",
        "dialogue_path",
        "dialogue_definition",
        "project_command_id",
        "entity_template_id",
        "asset_path",
        "color_rgb",
    }
)
_PARAMETER_SPEC_KEYS = frozenset(
    {
        "type",
        "required",
        "min",
        "max",
        "values",
        "items",
        "scope",
        "space",
        "area_parameter",
        "entity_parameter",
        "asset_kind",
    }
)
_ENTITY_PARAMETER_SCOPES = frozenset({"area", "global"})
_ENTITY_PARAMETER_SPACES = frozenset({"world", "screen"})
_ASSET_PARAMETER_KINDS = frozenset({"image", "audio", "json", "font"})
_ASSET_KIND_EXTENSIONS = {
    "image": {".png"},
    "audio": {".wav", ".ogg", ".mp3"},
    "json": {".json", ".json5"},
    "font": {".json", ".json5"},
}
_TEMPLATE_PARAMETER_BUILTINS = frozenset(
    {
        "self",
        "self_id",
        "refs",
        "ref_ids",
        "project",
        "current_area",
        "area",
        "camera",
        "from_x",
        "from_y",
        "to_x",
        "to_y",
        "blocking_entity_id",
    }
)


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
    dialogues = _parse_entity_dialogues(entity_data, source_name=source_name)
    persistence = _parse_entity_persistence(entity_data, source_name=source_name)
    visuals = _parse_entity_visuals(entity_data, tile_size=tile_size, source_name=source_name)
    entity_commands = _parse_entity_commands(entity_data)
    facing, authored_facing = _parse_entity_facing(entity_data, source_name=source_name)
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
        authored_facing=authored_facing,
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
        dialogues=dialogues,
        variables=variables,
        input_map=_parse_input_map(entity_data.get("input_map")),
        persistence=persistence,
    )
    entity.apply_default_visual_state()
    return entity


def _parse_entity_variables(entity_data: dict[str, Any], *, source_name: str) -> dict[str, Any]:
    """Parse one entity's variables object."""
    raw_variables = entity_data.get("variables", {})
    if raw_variables is None:
        return {}
    if not isinstance(raw_variables, dict):
        raise ValueError(f"{source_name} field 'variables' must be a JSON object.")
    return copy.deepcopy(raw_variables)


def _parse_entity_dialogues(
    entity_data: dict[str, Any],
    *,
    source_name: str,
    allow_parameter_tokens: bool = False,
) -> dict[str, dict[str, Any]]:
    """Parse one entity-owned named dialogue map."""
    raw_dialogues = entity_data.get("dialogues", {})
    if raw_dialogues is None:
        return {}
    if not isinstance(raw_dialogues, dict):
        raise ValueError(f"{source_name} field 'dialogues' must be a JSON object.")

    parsed: dict[str, dict[str, Any]] = {}
    for raw_dialogue_id, raw_dialogue_entry in raw_dialogues.items():
        dialogue_id = str(raw_dialogue_id).strip()
        if not dialogue_id:
            raise ValueError(f"{source_name} field 'dialogues' must not use blank dialogue ids.")
        location = f"{source_name} field 'dialogues.{dialogue_id}'"
        if not isinstance(raw_dialogue_entry, dict):
            raise ValueError(f"{location} must be a JSON object.")

        unknown_keys = sorted(
            str(key) for key in raw_dialogue_entry.keys()
            if str(key) not in {"dialogue_path", "dialogue_definition"}
        )
        if unknown_keys:
            joined = ", ".join(unknown_keys)
            raise ValueError(
                f"{location} contains unsupported field(s): {joined}."
            )

        raw_dialogue_path = raw_dialogue_entry.get("dialogue_path")
        raw_dialogue_definition = raw_dialogue_entry.get("dialogue_definition")
        has_dialogue_path = raw_dialogue_path is not None
        has_dialogue_definition = raw_dialogue_definition is not None
        if has_dialogue_path == has_dialogue_definition:
            raise ValueError(
                f"{location} must define exactly one of 'dialogue_path' or 'dialogue_definition'."
            )

        if has_dialogue_path:
            if (
                allow_parameter_tokens
                and isinstance(raw_dialogue_path, str)
                and _PARAMETER_TOKEN_RE.fullmatch(raw_dialogue_path.strip())
            ):
                parsed[dialogue_id] = {"dialogue_path": raw_dialogue_path.strip()}
                continue
            if not isinstance(raw_dialogue_path, str) or not raw_dialogue_path.strip():
                raise ValueError(f"{location}.dialogue_path must be a non-empty string.")
            parsed[dialogue_id] = {"dialogue_path": raw_dialogue_path.strip()}
            continue

        if (
            allow_parameter_tokens
            and isinstance(raw_dialogue_definition, str)
            and _PARAMETER_TOKEN_RE.fullmatch(raw_dialogue_definition.strip())
        ):
            parsed[dialogue_id] = {"dialogue_definition": raw_dialogue_definition.strip()}
            continue
        if not isinstance(raw_dialogue_definition, dict):
            raise ValueError(f"{location}.dialogue_definition must be a JSON object.")
        validate_authored_command_tree(
            raw_dialogue_definition,
            source_name=source_name,
            location=f"dialogues.{dialogue_id}.dialogue_definition",
        )
        parsed[dialogue_id] = {"dialogue_definition": copy.deepcopy(raw_dialogue_definition)}

    return parsed


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
) -> tuple[str, str | None]:
    """Parse one entity's top-level facing field."""
    raw_facing = entity_data.get("facing", _MISSING)
    if raw_facing is _MISSING:
        return ("down", None)
    facing = str(raw_facing).strip().lower()
    if facing not in {"up", "down", "left", "right"}:
        raise ValueError(
            f"{source_name} field 'facing' must be 'up', 'down', 'left', or 'right'."
        )
    return facing, facing


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

        raw_animations = raw_visual.get("animations", {})
        if raw_animations is None:
            raw_animations = {}
        if not isinstance(raw_animations, dict):
            raise ValueError(
                f"{source_name} visuals[{index}] field 'animations' must be a JSON object."
            )
        animations = _parse_visual_animations(
            raw_animations,
            source_name=f"{source_name} visuals[{index}]",
        )

        raw_frames = raw_visual.get("frames")
        if raw_frames is None:
            raw_frames = _default_visual_frames_from_animations(
                animations,
                default_animation=raw_visual.get("default_animation"),
            )
        if raw_frames is None:
            raw_frames = [0]
        if not isinstance(raw_frames, list):
            raise ValueError(f"{source_name} visuals[{index}] field 'frames' must be a JSON array.")
        frames = [int(frame) for frame in raw_frames]
        if not frames:
            raise ValueError(f"{source_name} visuals[{index}] field 'frames' must not be empty.")

        default_animation = _parse_optional_visual_animation_id(
            raw_visual.get("default_animation"),
            animations=animations,
            source_name=f"{source_name} visuals[{index}]",
        )
        default_animation_by_facing = _parse_default_animation_by_facing(
            raw_visual.get("default_animation_by_facing"),
            animations=animations,
            source_name=f"{source_name} visuals[{index}]",
        )

        frame_width = int(raw_visual.get("frame_width", tile_size))
        frame_height = int(raw_visual.get("frame_height", tile_size))
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError(f"{source_name} visuals[{index}] frame dimensions must be positive.")

        tint = _parse_color(raw_visual.get("tint"))
        current_frame = int(frames[0])
        flip_x = bool(raw_visual.get("flip_x", False))
        if default_animation is not None:
            default_clip = animations[default_animation]
            current_frame = default_clip.frames[0]
            if default_clip.flip_x is not None:
                flip_x = bool(default_clip.flip_x)
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
                current_frame=current_frame,
                flip_x=flip_x,
                visible=bool(raw_visual.get("visible", True)),
                tint=tint,
                offset_x=float(raw_visual.get("offset_x", 0.0)),
                offset_y=float(raw_visual.get("offset_y", 0.0)),
                draw_order=int(raw_visual.get("draw_order", index)),
                default_animation=default_animation,
                default_animation_by_facing=default_animation_by_facing,
                animations=animations,
            )
        )

    return visuals


def _parse_visual_animations(
    raw_animations: dict[str, Any],
    *,
    source_name: str,
) -> dict[str, VisualAnimationClip]:
    """Parse named visual animation clips."""
    animations: dict[str, VisualAnimationClip] = {}
    for raw_animation_id, raw_clip in raw_animations.items():
        animation_id = str(raw_animation_id).strip()
        if not animation_id:
            raise ValueError(f"{source_name} uses an empty animation id.")
        if not isinstance(raw_clip, dict):
            raise ValueError(f"{source_name} animations.{animation_id} must be a JSON object.")
        raw_frames = raw_clip.get("frames")
        if not isinstance(raw_frames, list):
            raise ValueError(
                f"{source_name} animations.{animation_id} field 'frames' must be a JSON array."
            )
        frames = [int(frame) for frame in raw_frames]
        if not frames:
            raise ValueError(
                f"{source_name} animations.{animation_id} field 'frames' must not be empty."
            )
        raw_flip_x = raw_clip.get("flip_x")
        if raw_flip_x is not None and not isinstance(raw_flip_x, bool):
            raise ValueError(
                f"{source_name} animations.{animation_id} field 'flip_x' must be a boolean."
            )
        raw_preserve_phase = raw_clip.get("preserve_phase", False)
        if not isinstance(raw_preserve_phase, bool):
            raise ValueError(
                f"{source_name} animations.{animation_id} field 'preserve_phase' must be a boolean."
            )
        animations[animation_id] = VisualAnimationClip(
            frames=frames,
            flip_x=None if raw_flip_x is None else bool(raw_flip_x),
            preserve_phase=raw_preserve_phase,
        )
    return animations


def _default_visual_frames_from_animations(
    animations: dict[str, VisualAnimationClip],
    *,
    default_animation: Any,
) -> list[int] | None:
    """Return fallback visual frames when a clip-only visual omits top-level frames."""
    if not animations:
        return None
    if default_animation is not None:
        animation_id = str(default_animation).strip()
        if animation_id in animations:
            return list(animations[animation_id].frames)
    first_animation_id = sorted(animations)[0]
    return list(animations[first_animation_id].frames)


def _parse_optional_visual_animation_id(
    raw_animation_id: Any,
    *,
    animations: dict[str, VisualAnimationClip],
    source_name: str,
) -> str | None:
    """Validate an optional default animation id."""
    if raw_animation_id is None:
        return None
    animation_id = str(raw_animation_id).strip()
    if not animation_id:
        raise ValueError(f"{source_name} field 'default_animation' must not be empty.")
    if animation_id not in animations:
        raise ValueError(
            f"{source_name} field 'default_animation' references unknown animation '{animation_id}'."
        )
    return animation_id


def _parse_default_animation_by_facing(
    raw_mapping: Any,
    *,
    animations: dict[str, VisualAnimationClip],
    source_name: str,
) -> dict[str, str]:
    """Validate an optional facing-to-default-animation mapping."""
    if raw_mapping is None:
        return {}
    if not isinstance(raw_mapping, dict):
        raise ValueError(
            f"{source_name} field 'default_animation_by_facing' must be a JSON object."
        )

    resolved: dict[str, str] = {}
    for raw_facing, raw_animation_id in raw_mapping.items():
        facing = str(raw_facing).strip().lower()
        if facing not in {"up", "down", "left", "right"}:
            raise ValueError(
                f"{source_name} field 'default_animation_by_facing' uses unknown facing '{raw_facing}'."
            )
        animation_id = _parse_optional_visual_animation_id(
            raw_animation_id,
            animations=animations,
            source_name=f"{source_name} default_animation_by_facing.{facing}",
        )
        if animation_id is None:
            raise ValueError(
                f"{source_name} field 'default_animation_by_facing.{facing}' must not be null."
            )
        resolved[facing] = animation_id
    return resolved


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
    if "parameter_specs" in instance_data:
        raise ValueError(
            f"{source_name} must not define 'parameter_specs'; define parameter specs on the entity template."
        )
    template_id = _normalize_optional_id(instance_data.get("template"))
    if template_id is None:
        if "parameters" in instance_data:
            raise ValueError(
                f"{source_name} must not define 'parameters' without a 'template'."
            )
        resolved = copy.deepcopy(instance_data)
    else:
        template_data = _load_entity_template(template_id, project=project)
        _validate_template_parameter_contract(
            template_data,
            source_name=f"template '{template_id}'",
            project=project,
        )
        instance_parameters = instance_data.get("parameters", {})
        if instance_parameters is None:
            instance_parameters = {}
        if not isinstance(instance_parameters, dict):
            raise ValueError(f"{source_name} field 'parameters' must be a JSON object.")
        raw_template_specs = template_data.get("parameter_specs")
        template_specs = _parse_parameter_specs(
            raw_template_specs,
            source_name=f"template '{template_id}'",
        )
        if raw_template_specs is not None:
            unknown_parameters = sorted(set(instance_parameters) - set(template_specs))
            if unknown_parameters:
                joined = ", ".join(unknown_parameters)
                raise ValueError(
                    f"{source_name} field 'parameters' defines unknown template parameter(s): {joined}."
                )
        resolved = _deep_merge(template_data, instance_data)

    parameters = resolved.pop("parameters", {})
    if parameters is None:
        parameters = {}
    if not isinstance(parameters, dict):
        raise ValueError(f"{source_name} field 'parameters' must be a JSON object.")
    parameter_specs = resolved.pop("parameter_specs", {})
    if parameter_specs is None:
        parameter_specs = {}
    if parameter_specs:
        parsed_specs = _parse_parameter_specs(parameter_specs, source_name=source_name)
        _validate_parameter_values(
            parameters,
            parsed_specs,
            source_name=source_name,
            project=project,
        )
    resolved.pop("template", None)
    substituted = _substitute_parameters(resolved, dict(parameters))
    if not isinstance(substituted, dict):
        raise ValueError(f"{source_name} must resolve to a JSON object after template expansion.")
    return substituted


def _validate_template_parameter_contract(
    template_data: dict[str, Any],
    *,
    source_name: str,
    project: ProjectContext,
) -> None:
    raw_specs = template_data.get("parameter_specs")
    if raw_specs is None:
        return
    specs = _parse_parameter_specs(raw_specs, source_name=source_name)
    defaults = template_data.get("parameters", {})
    if defaults is None:
        defaults = {}
    if not isinstance(defaults, dict):
        raise ValueError(f"{source_name} field 'parameters' must be a JSON object.")

    parameter_names: set[str] = set()
    _collect_parameter_tokens(template_data, parameter_names)
    parameter_names.update(str(key) for key in defaults.keys())

    missing_specs = sorted(parameter_names - set(specs))
    if missing_specs:
        joined = ", ".join(missing_specs)
        raise ValueError(
            f"{source_name} field 'parameter_specs' is missing spec(s) for parameter(s): {joined}."
        )

    unused_specs = sorted(set(specs) - parameter_names)
    if unused_specs:
        joined = ", ".join(unused_specs)
        raise ValueError(
            f"{source_name} field 'parameter_specs' defines unused parameter spec(s): {joined}."
        )

    _validate_parameter_values(
        defaults,
        specs,
        source_name=source_name,
        project=project,
        validate_required=False,
    )


def _parse_parameter_specs(
    raw_specs: Any,
    *,
    source_name: str,
) -> dict[str, dict[str, Any]]:
    if raw_specs is None:
        return {}
    if not isinstance(raw_specs, dict):
        raise ValueError(f"{source_name} field 'parameter_specs' must be a JSON object.")

    parsed: dict[str, dict[str, Any]] = {}
    for raw_name, raw_spec in raw_specs.items():
        name = str(raw_name).strip()
        if not name:
            raise ValueError(f"{source_name} field 'parameter_specs' cannot use a blank parameter name.")
        parsed[name] = _parse_one_parameter_spec(
            raw_spec,
            source_name=source_name,
            parameter_name=name,
        )
    for name, spec in parsed.items():
        entity_parameter = spec.get("entity_parameter")
        if isinstance(entity_parameter, str):
            target_spec = parsed.get(entity_parameter)
            if target_spec is None:
                raise ValueError(
                    f"{source_name} parameter_specs.{name}.entity_parameter references unknown parameter "
                    f"'{entity_parameter}'."
                )
            if target_spec.get("type") != "entity_id":
                raise ValueError(
                    f"{source_name} parameter_specs.{name}.entity_parameter must reference an entity_id parameter."
                )

        area_parameter = spec.get("area_parameter")
        if not isinstance(area_parameter, str):
            continue
        target_spec = parsed.get(area_parameter)
        if target_spec is None:
            raise ValueError(
                f"{source_name} parameter_specs.{name}.area_parameter references unknown parameter "
                f"'{area_parameter}'."
            )
        if target_spec.get("type") != "area_id":
            raise ValueError(
                f"{source_name} parameter_specs.{name}.area_parameter must reference an area_id parameter."
            )
    return parsed


def _parse_one_parameter_spec(
    raw_spec: Any,
    *,
    source_name: str,
    parameter_name: str,
) -> dict[str, Any]:
    location = f"{source_name} parameter_specs.{parameter_name}"
    if not isinstance(raw_spec, dict):
        raise ValueError(f"{location} must be a JSON object.")
    unknown_keys = sorted(set(raw_spec) - _PARAMETER_SPEC_KEYS)
    if unknown_keys:
        joined = ", ".join(str(key) for key in unknown_keys)
        raise ValueError(f"{location} uses unsupported key(s): {joined}.")

    raw_type = raw_spec.get("type")
    if not isinstance(raw_type, str) or not raw_type.strip():
        raise ValueError(f"{location}.type must be a non-empty string.")
    spec_type = raw_type.strip()
    if spec_type not in _PARAMETER_SPEC_TYPES:
        allowed = ", ".join(sorted(_PARAMETER_SPEC_TYPES))
        raise ValueError(f"{location}.type must be one of: {allowed}.")

    spec: dict[str, Any] = {"type": spec_type}
    if "required" in raw_spec:
        if not isinstance(raw_spec["required"], bool):
            raise ValueError(f"{location}.required must be true or false.")
        spec["required"] = raw_spec["required"]

    if "min" in raw_spec:
        if spec_type not in {"int", "number"}:
            raise ValueError(f"{location}.min is only supported for int and number parameters.")
        if not _is_number(raw_spec["min"]):
            raise ValueError(f"{location}.min must be a number.")
        spec["min"] = raw_spec["min"]

    if "max" in raw_spec:
        if spec_type not in {"int", "number"}:
            raise ValueError(f"{location}.max is only supported for int and number parameters.")
        if not _is_number(raw_spec["max"]):
            raise ValueError(f"{location}.max must be a number.")
        spec["max"] = raw_spec["max"]

    if "min" in spec and "max" in spec and float(spec["min"]) > float(spec["max"]):
        raise ValueError(f"{location}.min must be less than or equal to max.")

    if "values" in raw_spec:
        if spec_type != "enum":
            raise ValueError(f"{location}.values is only supported for enum parameters.")
        values = raw_spec["values"]
        if not isinstance(values, list) or not values:
            raise ValueError(f"{location}.values must be a non-empty JSON array.")
        spec["values"] = copy.deepcopy(values)

    if spec_type == "enum" and "values" not in spec:
        raise ValueError(f"{location}.values is required for enum parameters.")

    if "items" in raw_spec:
        if spec_type != "array":
            raise ValueError(f"{location}.items is only supported for array parameters.")
        spec["items"] = _parse_one_parameter_spec(
            raw_spec["items"],
            source_name=source_name,
            parameter_name=f"{parameter_name}.items",
        )

    if "scope" in raw_spec:
        if spec_type != "entity_id":
            raise ValueError(f"{location}.scope is only supported for entity_id parameters.")
        scope = str(raw_spec["scope"]).strip()
        if scope not in _ENTITY_PARAMETER_SCOPES:
            allowed = ", ".join(sorted(_ENTITY_PARAMETER_SCOPES))
            raise ValueError(f"{location}.scope must be one of: {allowed}.")
        spec["scope"] = scope

    if "space" in raw_spec:
        if spec_type != "entity_id":
            raise ValueError(f"{location}.space is only supported for entity_id parameters.")
        space = str(raw_spec["space"]).strip()
        if space not in _ENTITY_PARAMETER_SPACES:
            allowed = ", ".join(sorted(_ENTITY_PARAMETER_SPACES))
            raise ValueError(f"{location}.space must be one of: {allowed}.")
        spec["space"] = space

    if "area_parameter" in raw_spec:
        if spec_type != "entity_id":
            raise ValueError(f"{location}.area_parameter is only supported for entity_id parameters.")
        area_parameter = str(raw_spec["area_parameter"]).strip()
        if not area_parameter:
            raise ValueError(f"{location}.area_parameter must be a non-empty string.")
        spec["area_parameter"] = area_parameter

    if "entity_parameter" in raw_spec:
        if spec_type != "entity_command_id":
            raise ValueError(
                f"{location}.entity_parameter is only supported for entity_command_id parameters."
            )
        entity_parameter = str(raw_spec["entity_parameter"]).strip()
        if not entity_parameter:
            raise ValueError(f"{location}.entity_parameter must be a non-empty string.")
        spec["entity_parameter"] = entity_parameter

    if "asset_kind" in raw_spec:
        if spec_type != "asset_path":
            raise ValueError(f"{location}.asset_kind is only supported for asset_path parameters.")
        asset_kind = str(raw_spec["asset_kind"]).strip()
        if asset_kind not in _ASSET_PARAMETER_KINDS:
            allowed = ", ".join(sorted(_ASSET_PARAMETER_KINDS))
            raise ValueError(f"{location}.asset_kind must be one of: {allowed}.")
        spec["asset_kind"] = asset_kind

    return spec


def _validate_parameter_values(
    parameters: dict[str, Any],
    specs: dict[str, dict[str, Any]],
    *,
    source_name: str,
    project: ProjectContext,
    validate_required: bool = True,
) -> None:
    for name, spec in specs.items():
        has_value = name in parameters
        value = parameters.get(name)
        if _parameter_value_is_blank(value):
            if validate_required and bool(spec.get("required", False)):
                raise ValueError(f"{source_name} parameter '{name}' is required.")
            continue
        if not has_value:
            continue
        _validate_one_parameter_value(
            value,
            spec,
            parameter_name=name,
            source_name=source_name,
            project=project,
            all_parameters=parameters,
        )

    unknown_parameters = sorted(set(parameters) - set(specs))
    if unknown_parameters:
        joined = ", ".join(str(name) for name in unknown_parameters)
        raise ValueError(f"{source_name} defines unknown template parameter(s): {joined}.")


def _validate_one_parameter_value(
    value: Any,
    spec: dict[str, Any],
    *,
    parameter_name: str,
    source_name: str,
    project: ProjectContext,
    all_parameters: dict[str, Any],
) -> None:
    spec_type = str(spec["type"])
    location = f"{source_name} parameter '{parameter_name}'"

    if spec_type in {"string", "text"}:
        if not isinstance(value, str):
            raise ValueError(f"{location} must be a string.")
        return

    if spec_type == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{location} must be true or false.")
        return

    if spec_type == "int":
        if not _is_int(value):
            raise ValueError(f"{location} must be an integer.")
        _validate_numeric_bounds(int(value), spec, location=location)
        return

    if spec_type == "number":
        if not _is_number(value):
            raise ValueError(f"{location} must be a number.")
        _validate_numeric_bounds(float(value), spec, location=location)
        return

    if spec_type == "enum":
        if value not in spec["values"]:
            allowed = ", ".join(repr(item) for item in spec["values"])
            raise ValueError(f"{location} must be one of: {allowed}.")
        return

    if spec_type == "array":
        if not isinstance(value, list):
            raise ValueError(f"{location} must be a JSON array.")
        item_spec = spec.get("items")
        if isinstance(item_spec, dict):
            for index, item in enumerate(value):
                _validate_one_parameter_value(
                    item,
                    item_spec,
                    parameter_name=f"{parameter_name}[{index}]",
                    source_name=source_name,
                    project=project,
                    all_parameters=all_parameters,
                )
        return

    if spec_type == "json":
        return

    if spec_type == "dialogue_definition":
        if not isinstance(value, dict):
            raise ValueError(f"{location} must be a JSON object.")
        raw_segments = value.get("segments")
        if not isinstance(raw_segments, list):
            raise ValueError(f"{location}.segments must be a JSON array.")
        return

    if spec_type == "color_rgb":
        if (
            not isinstance(value, list)
            or len(value) != 3
            or not all(_is_int(channel) and 0 <= int(channel) <= 255 for channel in value)
        ):
            raise ValueError(f"{location} must be an RGB array of three integers from 0 to 255.")
        return

    if spec_type == "area_id":
        _validate_string_reference(value, location=location)
        if project.resolve_area_reference(str(value)) is None:
            raise ValueError(f"{location} references unknown area '{value}'.")
        return

    if spec_type == "item_id":
        _validate_string_reference(value, location=location)
        if project.find_item(str(value)) is None:
            raise ValueError(f"{location} references unknown item '{value}'.")
        return

    if spec_type == "project_command_id":
        _validate_string_reference(value, location=location)
        if project.find_command(str(value)) is None:
            raise ValueError(f"{location} references unknown project command '{value}'.")
        return

    if spec_type == "entity_template_id":
        _validate_string_reference(value, location=location)
        if project.find_entity_template(str(value)) is None:
            raise ValueError(f"{location} references unknown entity template '{value}'.")
        return

    if spec_type == "asset_path":
        _validate_string_reference(value, location=location)
        if project.resolve_asset(str(value)) is None:
            raise ValueError(f"{location} references unknown asset '{value}'.")
        asset_kind = spec.get("asset_kind")
        if isinstance(asset_kind, str):
            allowed_extensions = _ASSET_KIND_EXTENSIONS.get(asset_kind, set())
            if allowed_extensions and Path(str(value)).suffix.lower() not in allowed_extensions:
                raise ValueError(f"{location} must reference a {asset_kind} asset.")
        return

    if spec_type in {"dialogue_path", "entity_id", "entity_command_id"}:
        _validate_string_reference(value, location=location)
        if spec_type == "entity_id":
            _validate_entity_parameter_reference(
                str(value),
                spec,
                parameter_name=parameter_name,
                source_name=source_name,
                project=project,
                all_parameters=all_parameters,
            )
        elif spec_type == "entity_command_id":
            _validate_entity_command_parameter_reference(
                str(value),
                spec,
                parameter_name=parameter_name,
                source_name=source_name,
                project=project,
                all_parameters=all_parameters,
            )
        return


def _validate_numeric_bounds(value: float, spec: dict[str, Any], *, location: str) -> None:
    if "min" in spec and value < float(spec["min"]):
        raise ValueError(f"{location} must be greater than or equal to {spec['min']}.")
    if "max" in spec and value > float(spec["max"]):
        raise ValueError(f"{location} must be less than or equal to {spec['max']}.")


def _validate_string_reference(value: Any, *, location: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{location} must be a non-empty string.")


def _validate_entity_parameter_reference(
    entity_id: str,
    spec: dict[str, Any],
    *,
    parameter_name: str,
    source_name: str,
    project: ProjectContext,
    all_parameters: dict[str, Any],
) -> None:
    area_parameter = spec.get("area_parameter")
    target_area_id = None
    if isinstance(area_parameter, str):
        raw_area_id = all_parameters.get(area_parameter)
        if _parameter_value_is_blank(raw_area_id):
            raw_area_id = None
        elif not isinstance(raw_area_id, str):
            raise ValueError(
                f"{source_name} parameter '{parameter_name}' uses area_parameter '{area_parameter}', "
                "but that parameter is not a string area id."
            )
        else:
            target_area_id = str(raw_area_id).strip()

    record = _find_authored_entity_record(project, entity_id, area_id=target_area_id)
    if record is None:
        if target_area_id is not None and _find_authored_entity_record(project, entity_id) is not None:
            raise ValueError(
                f"{source_name} parameter '{parameter_name}' must reference an entity in area '{target_area_id}'."
            )
        raise ValueError(f"{source_name} parameter '{parameter_name}' references unknown entity '{entity_id}'.")
    expected_scope = spec.get("scope")
    if isinstance(expected_scope, str) and record.get("scope") != expected_scope:
        raise ValueError(
            f"{source_name} parameter '{parameter_name}' must reference a {expected_scope} entity."
        )
    expected_space = spec.get("space")
    if isinstance(expected_space, str) and record.get("space") != expected_space:
        raise ValueError(
            f"{source_name} parameter '{parameter_name}' must reference a {expected_space}-space entity."
        )
    if target_area_id is None:
        return
    if record.get("scope") != "area":
        raise ValueError(
            f"{source_name} parameter '{parameter_name}' uses area_parameter '{area_parameter}', "
            f"but entity '{entity_id}' is not an area entity."
        )
    if record.get("area_id") != target_area_id:
        raise ValueError(
            f"{source_name} parameter '{parameter_name}' must reference an entity in area '{target_area_id}'."
        )


def _validate_entity_command_parameter_reference(
    command_id: str,
    spec: dict[str, Any],
    *,
    parameter_name: str,
    source_name: str,
    project: ProjectContext,
    all_parameters: dict[str, Any],
) -> None:
    entity_parameter = spec.get("entity_parameter")
    if not isinstance(entity_parameter, str):
        return
    raw_entity_id = all_parameters.get(entity_parameter)
    if _parameter_value_is_blank(raw_entity_id):
        return
    if not isinstance(raw_entity_id, str):
        raise ValueError(
            f"{source_name} parameter '{parameter_name}' uses entity_parameter '{entity_parameter}', "
            "but that parameter is not a string entity id."
        )
    record = _find_authored_entity_record(project, raw_entity_id)
    if record is None:
        raise ValueError(
            f"{source_name} parameter '{parameter_name}' references command '{command_id}' on unknown entity '{raw_entity_id}'."
        )
    command_ids = _authored_entity_command_ids(project, record)
    if command_id not in command_ids:
        raise ValueError(
            f"{source_name} parameter '{parameter_name}' references unknown entity command '{command_id}' on entity '{raw_entity_id}'."
        )


def _find_authored_entity_record(
    project: ProjectContext,
    entity_id: str,
    *,
    area_id: str | None = None,
) -> dict[str, Any] | None:
    target = str(entity_id).strip()
    if not target:
        return None
    records = _authored_entity_index(project).get(target, [])
    if area_id is not None:
        for record in records:
            if record.get("scope") == "area" and record.get("area_id") == area_id:
                return record
        return None
    if records:
        return records[0]
    return None


def _authored_entity_index(project: ProjectContext) -> dict[str, list[dict[str, Any]]]:
    project_cache = _AUTHORED_ENTITY_INDEX_PROJECT_CACHE.get(id(project))
    if project_cache is not None and project_cache[0] is project:
        return project_cache[1]

    cache_key = _authored_entity_index_cache_key(project)
    cached = _AUTHORED_ENTITY_INDEX_CACHE.get(cache_key)
    if cached is not None:
        _AUTHORED_ENTITY_INDEX_PROJECT_CACHE[id(project)] = (project, cached)
        return cached

    index: dict[str, list[dict[str, Any]]] = {}
    for raw_entity in project.global_entities:
        if not isinstance(raw_entity, dict):
            continue
        entity_id = str(raw_entity.get("id", "")).strip()
        if not entity_id:
            continue
        index.setdefault(entity_id, []).append(
            {
                "raw": raw_entity,
                "scope": "global",
                "space": _resolve_authored_entity_space(raw_entity, project),
            }
        )

    for area_path in project.list_area_files():
        try:
            raw_area = load_json_data(area_path)
        except Exception:
            continue
        if not isinstance(raw_area, dict):
            continue
        raw_entities = raw_area.get("entities", [])
        if not isinstance(raw_entities, list):
            continue
        area_id = project.area_id(area_path)
        for raw_entity in raw_entities:
            if not isinstance(raw_entity, dict):
                continue
            entity_id = str(raw_entity.get("id", "")).strip()
            if not entity_id:
                continue
            index.setdefault(entity_id, []).append(
                {
                    "raw": raw_entity,
                    "scope": "area",
                    "space": _resolve_authored_entity_space(raw_entity, project),
                    "area_id": area_id,
                }
            )

    _AUTHORED_ENTITY_INDEX_CACHE[cache_key] = index
    _AUTHORED_ENTITY_INDEX_PROJECT_CACHE[id(project)] = (project, index)
    return index


def _authored_entity_index_cache_key(
    project: ProjectContext,
) -> tuple[Path, tuple[tuple[Path, int | None, int | None], ...]]:
    area_fingerprint: list[tuple[Path, int | None, int | None]] = []
    for area_path in project.list_area_files():
        resolved = area_path.resolve()
        try:
            stat = resolved.stat()
            area_fingerprint.append((resolved, int(stat.st_mtime_ns), int(stat.st_size)))
        except OSError:
            area_fingerprint.append((resolved, None, None))
    return (project.project_root.resolve(), tuple(area_fingerprint))


def _resolve_authored_entity_space(raw_entity: dict[str, Any], project: ProjectContext) -> str:
    raw_space = raw_entity.get("space")
    if isinstance(raw_space, str) and raw_space.strip():
        return raw_space.strip().lower()
    template_id = _normalize_optional_id(raw_entity.get("template"))
    if template_id is not None:
        try:
            template_data = _load_entity_template(template_id, project=project)
        except Exception:
            return "world"
        raw_template_space = template_data.get("space")
        if isinstance(raw_template_space, str) and raw_template_space.strip():
            return raw_template_space.strip().lower()
    return "world"


def _authored_entity_command_ids(project: ProjectContext, record: dict[str, Any]) -> set[str]:
    raw = record.get("raw")
    if not isinstance(raw, dict):
        return set()
    command_ids: set[str] = set()
    template_id = _normalize_optional_id(raw.get("template"))
    if template_id is not None:
        try:
            template_data = _load_entity_template(template_id, project=project)
        except Exception:
            template_data = {}
        raw_template_commands = template_data.get("entity_commands")
        if isinstance(raw_template_commands, dict):
            command_ids.update(str(command_id) for command_id in raw_template_commands.keys())
    raw_commands = raw.get("entity_commands")
    if isinstance(raw_commands, dict):
        command_ids.update(str(command_id) for command_id in raw_commands.keys())
    return command_ids


def _parameter_value_is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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
        for key, item in value.items():
            if key == "parameter_specs":
                continue
            _collect_parameter_tokens(item, found)
    elif isinstance(value, list):
        for item in value:
            _collect_parameter_tokens(item, found)
    elif isinstance(value, str):
        match = _PARAMETER_TOKEN_RE.fullmatch(value)
        if match:
            name = match.group("braced") or match.group("plain")
            if name and name not in _TEMPLATE_PARAMETER_BUILTINS:
                found.add(name)


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
                project=project,
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


def _validate_entity_template_raw(
    raw_template: dict[str, Any],
    *,
    source_name: str,
    project: ProjectContext,
) -> None:
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

    _validate_template_parameter_contract(
        raw_template,
        source_name=source_name,
        project=project,
    )
    _parse_entity_dialogues(
        raw_template,
        source_name=source_name,
        allow_parameter_tokens=True,
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
