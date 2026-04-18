"""Check local Markdown links for missing repo-local targets."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "archive",
    "archived_editor",
    "python_puzzle_engine.egg-info",
    "site",
}
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)|!\[[^\]]*\]\(([^)]+)\)")


@dataclass(frozen=True)
class MarkdownLinkIssue:
    """One broken local Markdown link."""

    source_path: Path
    line_number: int
    target: str
    message: str


def _default_scan_paths(repo_root: Path) -> list[Path]:
    """Return the default Markdown roots for this repo."""
    return [repo_root]


def _iter_markdown_files(paths: list[Path], *, repo_root: Path) -> list[Path]:
    """Return Markdown files under the selected scan roots."""
    files: set[Path] = set()
    for raw_path in paths:
        path = raw_path if raw_path.is_absolute() else repo_root / raw_path
        resolved = path.resolve()
        if resolved.is_file():
            if resolved.suffix.lower() == ".md":
                files.add(resolved)
            continue
        if not resolved.exists():
            continue
        for candidate in resolved.rglob("*.md"):
            if any(part in DEFAULT_EXCLUDED_DIRS for part in candidate.parts):
                continue
            files.add(candidate.resolve())
    return sorted(files)


def _iter_markdown_links(markdown_path: Path) -> list[tuple[int, str]]:
    """Return Markdown link targets with line numbers, skipping fenced blocks."""
    links: list[tuple[int, str]] = []
    in_fence = False
    for line_number, line in enumerate(
        markdown_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in LINK_RE.finditer(line):
            target = match.group(1) or match.group(2)
            if target:
                links.append((line_number, target.strip()))
    return links


def _normalize_target(raw_target: str) -> str:
    """Strip Markdown wrappers and optional titles from one target."""
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    if ' "' in target and target.endswith('"'):
        target = target.rsplit(' "', 1)[0]
    if " '" in target and target.endswith("'"):
        target = target.rsplit(" '", 1)[0]
    return target.strip()


def _is_external_target(target: str) -> bool:
    """Return whether one Markdown target is external/non-file."""
    if not target or target.startswith("#"):
        return True
    parsed = urlparse(target)
    return parsed.scheme in {"data", "http", "https", "mailto", "tel"}


def _resolve_local_target(source_path: Path, target: str) -> Path | None:
    """Resolve one local Markdown target relative to the source file."""
    normalized = _normalize_target(target)
    if _is_external_target(normalized):
        return None
    target_path, _, _anchor = normalized.partition("#")
    if not target_path:
        return None
    target_path = unquote(target_path)
    return (source_path.parent / target_path).resolve()


def find_markdown_link_issues(
    paths: list[Path] | None = None,
    *,
    repo_root: Path | None = None,
) -> list[MarkdownLinkIssue]:
    """Scan Markdown files and return any missing local link targets."""
    active_repo_root = (repo_root or REPO_ROOT).resolve()
    scan_paths = paths or _default_scan_paths(active_repo_root)
    issues: list[MarkdownLinkIssue] = []
    for markdown_path in _iter_markdown_files(scan_paths, repo_root=active_repo_root):
        for line_number, target in _iter_markdown_links(markdown_path):
            resolved = _resolve_local_target(markdown_path, target)
            if resolved is None or resolved.exists():
                continue
            issues.append(
                MarkdownLinkIssue(
                    source_path=markdown_path,
                    line_number=line_number,
                    target=target,
                    message=f"missing local target: {target}",
                )
            )
    return issues


def main(argv: list[str] | None = None) -> int:
    """Run the Markdown link checker CLI."""
    parser = argparse.ArgumentParser(
        description="Check repo-local Markdown links for missing local targets.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files or directories to scan. Defaults to the active repo docs roots.",
    )
    args = parser.parse_args(argv)

    active_repo_root = REPO_ROOT.resolve()
    issues = find_markdown_link_issues(args.paths, repo_root=active_repo_root)
    if not issues:
        print("Markdown link check passed.")
        return 0

    for issue in issues:
        try:
            display_path = issue.source_path.relative_to(active_repo_root)
        except ValueError:
            display_path = issue.source_path
        print(
            f"{display_path}:{issue.line_number}: {issue.message}",
            file=sys.stderr,
        )
    print(
        f"Markdown link check failed with {len(issues)} issue(s).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
