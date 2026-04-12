"""JSON/JSON5 authoring file helpers.

The supported authoring convention is intentionally narrow: comments may live
before or after the root JSON value as file-level notes. Comments inside the
root object/array are rejected so structured editor rewrites can preserve notes
without needing to attach comments to individual fields.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import json5


JSON_DATA_SUFFIXES = (".json", ".json5")
DEFAULT_JSON5_FILE_HEADER = "/*\n  NOTES\n\n  Add file-level notes here.\n*/\n\n"

_JSON5_ERROR_RE = re.compile(r":(?P<line>\d+).*column (?P<column>\d+)")


@dataclass(frozen=True)
class JsonFileParts:
    """One JSON/JSON5 file split into file-level notes and body text."""

    leading_text: str
    body_text: str
    trailing_text: str


class JsonDataDecodeError(ValueError):
    """Raised when an authored JSON/JSON5 file cannot be parsed."""

    def __init__(
        self,
        source_name: str,
        msg: str,
        *,
        lineno: int | None = None,
        colno: int | None = None,
    ) -> None:
        self.source_name = source_name
        self.msg = msg
        self.lineno = lineno or 1
        self.colno = colno or 1
        super().__init__(
            f"{source_name}: {msg} at line {self.lineno}, column {self.colno}"
        )


def is_json_data_file(path: Path) -> bool:
    """Return True when *path* uses a supported authored data suffix."""

    return path.suffix.lower() in JSON_DATA_SUFFIXES


def iter_json_data_files(root: Path) -> list[Path]:
    """Return sorted ``.json`` and ``.json5`` files under *root*."""

    if not root.is_dir():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file() and is_json_data_file(path))


def strip_json_data_suffix(path: Path) -> Path:
    """Strip one supported JSON data suffix from *path* if present."""

    return path.with_suffix("") if is_json_data_file(path) else path


def with_json_data_suffix(path: Path, *, default_suffix: str = ".json5") -> Path:
    """Return *path* with a JSON data suffix, preserving explicit suffixes."""

    if is_json_data_file(path):
        return path
    if default_suffix.lower() not in JSON_DATA_SUFFIXES:
        raise ValueError(f"Unsupported JSON data suffix '{default_suffix}'.")
    return path.with_suffix(default_suffix)


def json_data_path_candidates(path: Path) -> list[Path]:
    """Return possible authored data paths for a suffix-less *path*."""

    if is_json_data_file(path):
        return [path]
    return [path.with_suffix(".json"), path.with_suffix(".json5")]


def resolve_json_data_file(
    base_path: Path,
    *,
    basename: str | None = None,
    description: str = "JSON data file",
) -> Path:
    """Resolve one ``.json`` or ``.json5`` file, rejecting ambiguous matches."""

    candidates: Iterable[Path]
    if basename is None:
        candidates = json_data_path_candidates(base_path)
    else:
        candidates = json_data_path_candidates(base_path / basename)
    existing = [candidate for candidate in candidates if candidate.is_file()]
    if not existing:
        target = base_path / basename if basename is not None else base_path
        raise FileNotFoundError(f"{description} '{target}' was not found.")
    if len(existing) > 1:
        formatted = ", ".join(str(path) for path in existing)
        raise ValueError(f"Ambiguous {description} matches: {formatted}")
    return existing[0]


def load_json_data(path: Path) -> Any:
    """Load an authored JSON/JSON5 data file."""

    return loads_json_data(path.read_text(encoding="utf-8"), source_name=str(path))


def loads_json_data(text: str, *, source_name: str = "<string>") -> Any:
    """Parse authored JSON/JSON5 data with file-level comments."""

    parts = split_json_file_text(text, source_name=source_name)
    try:
        return json5.loads(parts.body_text)
    except ValueError as exc:
        lineno, colno = _decode_json5_location(exc)
        if lineno is not None:
            lineno += parts.leading_text.count("\n")
            if "\n" not in parts.leading_text and colno is not None:
                colno += len(parts.leading_text)
        raise JsonDataDecodeError(
            source_name,
            _strip_json5_source_prefix(str(exc)),
            lineno=lineno,
            colno=colno,
        ) from exc


def split_json_file_text(text: str, *, source_name: str = "<string>") -> JsonFileParts:
    """Split an authored JSON/JSON5 file into leading notes, body, and tail."""

    body_start = _skip_outer_whitespace_and_comments(text, 0, source_name=source_name)
    if body_start >= len(text):
        raise JsonDataDecodeError(source_name, "empty JSON data")
    if text[body_start] not in "{[":
        lineno, colno = _line_col(text, body_start)
        raise JsonDataDecodeError(
            source_name,
            "authored JSON data must start with an object or array after file-level comments",
            lineno=lineno,
            colno=colno,
        )

    body_end = _find_root_container_end(text, body_start, source_name=source_name)
    trailing_end = _skip_outer_whitespace_and_comments(
        text,
        body_end,
        source_name=source_name,
    )
    if trailing_end != len(text):
        lineno, colno = _line_col(text, trailing_end)
        raise JsonDataDecodeError(
            source_name,
            "unexpected content after root JSON value; only file-level comments are allowed there",
            lineno=lineno,
            colno=colno,
        )

    return JsonFileParts(
        leading_text=text[:body_start],
        body_text=text[body_start:body_end],
        trailing_text=text[body_end:],
    )


def compose_json_file_text(
    body_text: str,
    *,
    original_text: str | None = None,
    add_default_header: bool = False,
) -> str:
    """Return formatted body text wrapped in preserved file-level comments."""

    leading_text = ""
    trailing_text = ""
    if original_text is not None:
        parts = split_json_file_text(original_text)
        leading_text = parts.leading_text
        trailing_text = parts.trailing_text

    if add_default_header and not leading_text.strip():
        leading_text = DEFAULT_JSON5_FILE_HEADER

    body = body_text.rstrip()
    output = leading_text
    if output and not output.endswith(("\n", "\r")):
        output += "\n"
    output += body

    if trailing_text:
        if not output.endswith(("\n", "\r")) and not trailing_text[0].isspace():
            output += "\n"
        output += trailing_text
        if not output.endswith(("\n", "\r")):
            output += "\n"
        return output

    return f"{output}\n"


def dumps_for_clone(value: Any) -> Any:
    """Return a JSON-serializable deep copy for simple authored data values."""

    return json.loads(json.dumps(value))


def _skip_outer_whitespace_and_comments(
    text: str,
    index: int,
    *,
    source_name: str,
) -> int:
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index + 2)
            return len(text) if newline == -1 else _skip_outer_whitespace_and_comments(
                text,
                newline + 1,
                source_name=source_name,
            )
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end == -1:
                lineno, colno = _line_col(text, index)
                raise JsonDataDecodeError(
                    source_name,
                    "unterminated file-level block comment",
                    lineno=lineno,
                    colno=colno,
                )
            index = end + 2
            continue
        return index
    return index


def _find_root_container_end(text: str, start: int, *, source_name: str) -> int:
    expected_stack: list[str] = []
    quote: str | None = None
    escaped = False
    index = start

    while index < len(text):
        char = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue

        if char in {'"', "'"}:
            quote = char
            index += 1
            continue
        if text.startswith("//", index) or text.startswith("/*", index):
            lineno, colno = _line_col(text, index)
            raise JsonDataDecodeError(
                source_name,
                "comments are only supported before or after the root JSON value",
                lineno=lineno,
                colno=colno,
            )
        if char == "{":
            expected_stack.append("}")
        elif char == "[":
            expected_stack.append("]")
        elif char in "}]":
            if not expected_stack or char != expected_stack[-1]:
                lineno, colno = _line_col(text, index)
                raise JsonDataDecodeError(
                    source_name,
                    f"unexpected closing delimiter '{char}'",
                    lineno=lineno,
                    colno=colno,
                )
            expected_stack.pop()
            if not expected_stack:
                return index + 1
        index += 1

    lineno, colno = _line_col(text, start)
    raise JsonDataDecodeError(
        source_name,
        "unterminated root JSON object or array",
        lineno=lineno,
        colno=colno,
    )


def _line_col(text: str, index: int) -> tuple[int, int]:
    line = text.count("\n", 0, index) + 1
    previous_newline = text.rfind("\n", 0, index)
    column = index + 1 if previous_newline == -1 else index - previous_newline
    return line, column


def _decode_json5_location(error: ValueError) -> tuple[int | None, int | None]:
    match = _JSON5_ERROR_RE.search(str(error))
    if match is None:
        return None, None
    return int(match.group("line")), int(match.group("column"))


def _strip_json5_source_prefix(message: str) -> str:
    prefix_match = re.match(r"^<string>:\d+\s+", message)
    if prefix_match is None:
        return message
    return message[prefix_match.end() :]
