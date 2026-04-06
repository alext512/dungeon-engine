from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from area_editor.documents.area_document import EntityDocument


@dataclass(frozen=True)
class _EntityIdUsage:
    entity_id: str
    kind: str
    area_id: str | None = None
    file_path: Path | None = None


@dataclass(frozen=True)
class _JsonReferenceFileUpdate:
    file_path: Path
    updated_text: str
    changed_paths: tuple[str, ...]


@dataclass(frozen=True)
class _JsonReferenceUsage:
    file_path: Path
    matched_paths: tuple[str, ...]


@dataclass(frozen=True)
class _TileClipboard:
    width: int
    height: int
    grid: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class _ReferenceKeyMatcher:
    exact_keys: frozenset[str]
    suffix_keys: frozenset[str] = frozenset()

    def matches(self, key: str) -> bool:
        return key in self.exact_keys or any(
            key.endswith(suffix) for suffix in self.suffix_keys
        )


def _relative_content_name(content_id: str, prefix: str | None) -> str | None:
    normalized = content_id.replace("\\", "/")
    stripped_prefix = (prefix or "").strip("/")
    if stripped_prefix:
        expected_prefix = f"{stripped_prefix}/"
        if not normalized.startswith(expected_prefix):
            return None
        relative_name = normalized[len(expected_prefix) :].strip("/")
    else:
        relative_name = normalized.strip("/")
    return relative_name or None


def _root_dir_for_content_file(file_path: Path, roots: list[Path]) -> Path | None:
    resolved = file_path.resolve()
    for root_dir in roots:
        try:
            resolved.relative_to(root_dir.resolve())
            return root_dir.resolve()
        except ValueError:
            continue
    return None


def _world_entity_sort_key(entity: EntityDocument) -> tuple:
    sort_bucket = 1 if entity.y_sort else 0
    sort_y = float(entity.y + 1 + entity.sort_y_offset) if entity.y_sort else 0.0
    return (
        entity.render_order,
        sort_bucket,
        sort_y,
        entity.stack_order,
        entity.x,
        entity.id,
    )


def _discover_prefixed_json_content_ids(root_dirs: list[Path], *, prefix: str) -> list[str]:
    entries: list[str] = []
    seen: set[Path] = set()
    for directory in root_dirs:
        if not directory.is_dir():
            continue
        for file_path in sorted(directory.rglob("*.json")):
            resolved = file_path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                relative = resolved.relative_to(directory.resolve())
            except ValueError:
                relative = resolved.name
            relative_name = str(Path(relative).with_suffix("")).replace("\\", "/")
            entries.append(f"{prefix}/{relative_name}".strip("/"))
    return sorted(entries)
