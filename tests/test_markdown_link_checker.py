from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import check_markdown_links


class MarkdownLinkCheckerTests(unittest.TestCase):
    def test_missing_local_target_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            doc = repo_root / "README.md"
            doc.write_text("[Broken](docs/missing.md)\n", encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with (
                redirect_stdout(stdout),
                redirect_stderr(stderr),
                patch.object(check_markdown_links, "REPO_ROOT", repo_root),
            ):
                exit_code = check_markdown_links.main([])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn(
            "README.md:1: missing local target: docs/missing.md",
            stderr.getvalue(),
        )

    def test_external_urls_and_anchors_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            doc = repo_root / "README.md"
            doc.write_text(
                "\n".join(
                    [
                        "[Site](https://example.com)",
                        "[Mail](mailto:test@example.com)",
                        "[Section](#local-anchor)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            with (
                redirect_stdout(stdout),
                redirect_stderr(stderr),
                patch.object(check_markdown_links, "REPO_ROOT", repo_root),
            ):
                exit_code = check_markdown_links.main([])

        self.assertEqual(exit_code, 0)
        self.assertIn("Markdown link check passed.", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_links_inside_fenced_code_blocks_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            doc = repo_root / "README.md"
            doc.write_text(
                "\n".join(
                    [
                        "```md",
                        "[Example](docs/missing.md)",
                        "```",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            with (
                redirect_stdout(stdout),
                redirect_stderr(stderr),
                patch.object(check_markdown_links, "REPO_ROOT", repo_root),
            ):
                exit_code = check_markdown_links.main([])

        self.assertEqual(exit_code, 0)
        self.assertIn("Markdown link check passed.", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_current_repo_markdown_links_resolve(self) -> None:
        issues = check_markdown_links.find_markdown_link_issues()
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
