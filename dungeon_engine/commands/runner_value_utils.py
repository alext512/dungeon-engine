"""Generic value-resolution helpers shared by the command runner."""

from __future__ import annotations

import copy
from pathlib import Path
import random
from typing import Any

from dungeon_engine.json_io import json_data_path_candidates, load_json_data


_FALLBACK_RANDOM_GENERATOR = random.Random()


def lookup_nested_value(value: Any, path_parts: list[str]) -> Any:
    """Resolve a nested dict/list path against a Python value."""
    current = value
    for part in path_parts:
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(f"Unknown key '{part}'.")
            current = current[part]
            continue
        if isinstance(current, list):
            try:
                index = int(part)
            except ValueError as exc:
                raise KeyError(f"Expected list index, got '{part}'.") from exc
            try:
                current = current[index]
            except IndexError as exc:
                raise KeyError(f"List index '{index}' is out of range.") from exc
            continue
        raise KeyError(f"Cannot descend into '{part}'.")
    return current


def resolve_json_file_path(context: Any, path: str) -> Path:
    """Resolve one JSON file path relative to the active project when needed."""
    resolved_path = Path(str(path).strip())
    if not resolved_path.is_absolute():
        if context.project is not None:
            resolved_path = context.project.project_root / resolved_path
        else:
            resolved_path = Path.cwd() / resolved_path
    resolved_path = resolved_path.resolve()
    if resolved_path.exists():
        return resolved_path
    matches = [candidate.resolve() for candidate in json_data_path_candidates(resolved_path) if candidate.is_file()]
    if len(matches) == 1:
        return matches[0]
    return resolved_path


def load_json_file(context: Any, path: Path) -> Any:
    """Load one JSON file through the current runtime context's small cache."""
    cached = context.json_file_cache.get(path)
    if cached is None:
        cached = load_json_data(path)
        context.json_file_cache[path] = cached
    return copy.deepcopy(cached)


def build_text_window(
    lines: Any,
    *,
    start: int = 0,
    max_lines: int = 1,
    separator: str = "\n",
) -> dict[str, Any]:
    """Return one visible text window plus simple metadata."""
    if lines is None:
        normalized_lines: list[str] = []
    elif isinstance(lines, str):
        normalized_lines = [str(lines)]
    elif isinstance(lines, (list, tuple)):
        normalized_lines = [str(item) for item in lines]
    else:
        raise TypeError(
            "Text-window value source requires lines to be a list, tuple, string, or null."
        )

    resolved_start = max(0, int(start))
    resolved_max_lines = max(0, int(max_lines))
    visible_lines = normalized_lines[resolved_start : resolved_start + resolved_max_lines]
    return {
        "visible_lines": visible_lines,
        "visible_text": str(separator).join(visible_lines),
        "has_more": resolved_start + resolved_max_lines < len(normalized_lines),
        "total_lines": len(normalized_lines),
    }


def extract_collection_item(
    value: Any,
    *,
    index: int | None = None,
    key: str | None = None,
    default: Any = None,
) -> Any:
    """Return one list/tuple or dict item with a consistent defaulting contract."""
    extracted_value = copy.deepcopy(default)
    if key is not None:
        if value is None:
            return extracted_value
        if not isinstance(value, dict):
            raise TypeError("Collection item lookup with key requires a dict value.")
        if key in value:
            return copy.deepcopy(value[key])
        return extracted_value

    if index is None:
        raise ValueError("Collection item lookup requires either key or index.")
    if value is None:
        return extracted_value
    if not isinstance(value, (list, tuple)):
        raise TypeError("Collection item lookup with index requires a list or tuple value.")
    resolved_index = int(index)
    if resolved_index < 0:
        resolved_index += len(value)
    if 0 <= resolved_index < len(value):
        return copy.deepcopy(value[resolved_index])
    return extracted_value


def coerce_numeric_value(value: Any, *, source_name: str) -> int | float:
    """Return one numeric value or raise a clear error for value-source math helpers."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{source_name} value source expects numeric values.")
    return value


def coerce_integer_value(value: Any, *, source_name: str, field_name: str) -> int:
    """Return one integer-like value or raise a clear error."""
    numeric_value = coerce_numeric_value(value, source_name=source_name)
    if isinstance(numeric_value, float) and not numeric_value.is_integer():
        raise TypeError(f"{source_name} {field_name} expects an integer value.")
    return int(numeric_value)


def resolve_sum_value(resolved_source: Any) -> int | float:
    """Return the numeric sum of a small authored value list."""
    if not isinstance(resolved_source, (list, tuple)):
        raise TypeError("$sum value source requires a list or tuple.")
    numeric_values = [coerce_numeric_value(value, source_name="$sum") for value in resolved_source]
    if any(isinstance(value, float) for value in numeric_values):
        return float(sum(float(value) for value in numeric_values))
    return int(sum(int(value) for value in numeric_values))


def resolve_product_value(resolved_source: Any) -> int | float:
    """Return the numeric product of a small authored value list."""
    if not isinstance(resolved_source, (list, tuple)):
        raise TypeError("$product value source requires a list or tuple.")
    numeric_values = [coerce_numeric_value(value, source_name="$product") for value in resolved_source]
    if not numeric_values:
        raise ValueError("$product value source requires at least one value.")
    product: int | float = 1
    for value in numeric_values:
        product *= value
    if any(isinstance(value, float) for value in numeric_values):
        return float(product)
    return int(product)


def resolve_join_text_value(resolved_source: Any) -> str:
    """Join a small authored value list into one text string."""
    if not isinstance(resolved_source, (list, tuple)):
        raise TypeError("$join_text value source requires a list or tuple.")
    return "".join("" if value is None else str(value) for value in resolved_source)


def resolve_slice_collection_value(resolved_source: Any) -> list[Any]:
    """Return a bounded list slice from a list/tuple value."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$slice_collection value source requires a JSON object.")
    collection = resolved_source.get("value")
    if collection is None:
        return []
    if not isinstance(collection, (list, tuple)):
        raise TypeError("$slice_collection value source requires a list or tuple value.")
    start = int(resolved_source.get("start", 0))
    count = resolved_source.get("count")
    if start < 0:
        start = max(0, len(collection) + start)
    if count is None:
        end = len(collection)
    else:
        resolved_count = int(count)
        if resolved_count <= 0:
            return []
        end = start + resolved_count
    return [copy.deepcopy(item) for item in list(collection)[start:end]]


def resolve_wrap_index_value(resolved_source: Any) -> int:
    """Wrap one integer index around a positive collection size."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$wrap_index value source requires a JSON object.")
    count = int(resolved_source.get("count", 0))
    default = int(resolved_source.get("default", 0))
    if count <= 0:
        return default
    value = int(resolved_source.get("value", default))
    return value % count


def resolve_and_value(resolved_source: Any) -> bool:
    """Return True when every authored value in the list is truthy."""
    if not isinstance(resolved_source, (list, tuple)):
        raise TypeError("$and value source requires a list or tuple.")
    return all(bool(value) for value in resolved_source)


def resolve_or_value(resolved_source: Any) -> bool:
    """Return True when any authored value in the list is truthy."""
    if not isinstance(resolved_source, (list, tuple)):
        raise TypeError("$or value source requires a list or tuple.")
    return any(bool(value) for value in resolved_source)


def resolve_not_value(resolved_source: Any) -> bool:
    """Return the authored truthiness negation of one value."""
    return not bool(resolved_source)


def runtime_random_generator(context: Any) -> Any:
    """Return the active RNG for authored runtime helpers."""
    if context.random_generator is not None:
        return context.random_generator
    return _FALLBACK_RANDOM_GENERATOR


def resolve_random_int_value(context: Any, resolved_source: Any) -> int:
    """Return one inclusive authored random integer."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$random_int value source requires a JSON object.")
    if "min" not in resolved_source or "max" not in resolved_source:
        raise ValueError("$random_int value source requires both min and max.")
    minimum = coerce_integer_value(
        resolved_source.get("min"),
        source_name="$random_int",
        field_name="min",
    )
    maximum = coerce_integer_value(
        resolved_source.get("max"),
        source_name="$random_int",
        field_name="max",
    )
    if minimum > maximum:
        raise ValueError("$random_int value source requires min <= max.")
    return int(runtime_random_generator(context).randint(minimum, maximum))


def resolve_random_choice_value(context: Any, resolved_source: Any) -> Any:
    """Return one random collection item or the supplied default."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$random_choice value source requires a JSON object.")
    collection = resolved_source.get("value")
    if collection is None:
        return copy.deepcopy(resolved_source.get("default"))
    if not isinstance(collection, (list, tuple)):
        raise TypeError("$random_choice value source requires a list or tuple value.")
    if not collection:
        return copy.deepcopy(resolved_source.get("default"))
    return copy.deepcopy(runtime_random_generator(context).choice(list(collection)))


def resolve_collection_field_value(item: Any, field_path: str | None) -> Any:
    """Resolve one optional dotted field path against a collection item."""
    if field_path in (None, ""):
        return item
    parts = [part for part in str(field_path).split(".") if part]
    return lookup_nested_value(item, parts)


def collection_comparator(op: str) -> Any:
    """Return a small generic comparator for collection helpers."""
    comparators = {
        "eq": lambda left, right: left == right,
        "neq": lambda left, right: left != right,
        "gt": lambda left, right: left > right,
        "gte": lambda left, right: left >= right,
        "lt": lambda left, right: left < right,
        "lte": lambda left, right: left <= right,
    }
    comparator = comparators.get(str(op))
    if comparator is None:
        raise ValueError(f"Unknown comparison operator '{op}'.")
    return comparator


def resolve_find_in_collection_value(resolved_source: Any) -> Any:
    """Return the first matching collection item or the supplied default."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$find_in_collection value source requires a JSON object.")
    collection = resolved_source.get("value")
    if collection is None:
        return copy.deepcopy(resolved_source.get("default"))
    if not isinstance(collection, (list, tuple)):
        raise TypeError("$find_in_collection value source requires a list or tuple value.")
    comparator = collection_comparator(str(resolved_source.get("op", "eq")))
    field_path = resolved_source.get("field")
    match_value = resolved_source.get("match")
    for item in collection:
        try:
            candidate_value = resolve_collection_field_value(item, field_path)
        except KeyError:
            continue
        if comparator(candidate_value, match_value):
            return copy.deepcopy(item)
    return copy.deepcopy(resolved_source.get("default"))


def resolve_any_in_collection_value(resolved_source: Any) -> bool:
    """Return True when any collection item matches the supplied predicate."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$any_in_collection value source requires a JSON object.")
    collection = resolved_source.get("value")
    if collection is None:
        return False
    if not isinstance(collection, (list, tuple)):
        raise TypeError("$any_in_collection value source requires a list or tuple value.")
    comparator = collection_comparator(str(resolved_source.get("op", "eq")))
    field_path = resolved_source.get("field")
    match_value = resolved_source.get("match")
    for item in collection:
        try:
            candidate_value = resolve_collection_field_value(item, field_path)
        except KeyError:
            continue
        if comparator(candidate_value, match_value):
            return True
    return False
