"""Tests for the detail-view README resolver/renderer. Offline: local
fixture files and an injected fake http_get (no network)."""

import tempfile
import unittest
from pathlib import Path

try:
    import gas_auditor.web.readme  # noqa: F401
except RuntimeError:
    raise unittest.SkipTest("web extra not installed")

from gas_auditor.web.readme import (
    candidate_for_row,
    render_markdown,
    resolve_readme,
)


def row(**over):
    base = {"script_id": "S1", "github_repo": "justin/invoice-bot",
            "github_repo_url": "https://github.com/justin/invoice-bot"}
    base.update(over)
    return base


def cand(**over):
    base = {"name": "invoice-bot", "full_name": "justin/invoice-bot",
            "html_url": "https://github.com/justin/invoice-bot",
            "local_path": "", "readme_path": "", "default_branch": ""}
    base.update(over)
    return base


class FakeResp:
    def __init__(self, status, text=""):
        self.status_code = status
        self.text = text


class TestResolve(unittest.TestCase):
    def test_no_repo_is_none_state(self):
        r = resolve_readme(row(github_repo=""), None)
        self.assertEqual(r["state"], "none")
        self.assertIn("No GitHub association", r["message"])

    def test_local_readme_wins_and_renders(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "README.md"
            p.write_text("# Invoice Bot\n\nDoes **invoices**.\n")
            r = resolve_readme(row(), cand(readme_path=str(p)))
        self.assertEqual(r["state"], "ok")
        self.assertIn("<h1>Invoice Bot</h1>", r["html"])
        self.assertIn("<strong>invoices</strong>", r["html"])
        self.assertIn("local checkout", r["source"])

    def test_local_path_root_readme_found(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "README.md").write_text("# Root Readme\n")
            r = resolve_readme(row(), cand(local_path=td))
        self.assertEqual(r["state"], "ok")
        self.assertIn("Root Readme", r["html"])

    def test_remote_fallback_main_then_master(self):
        calls = []

        def fake_get(url):
            calls.append(url)
            if url.endswith("/main/README.md"):
                return FakeResp(404)
            return FakeResp(200, "# From Master\n")

        r = resolve_readme(row(), cand(), http_get=fake_get)
        self.assertEqual(r["state"], "ok")
        self.assertIn("From Master", r["html"])
        self.assertIn("master", r["source"])
        self.assertEqual(len(calls), 2)

    def test_remote_default_branch_tried_first(self):
        def fake_get(url):
            return FakeResp(200, "# Dev\n") if "/dev/" in url else FakeResp(404)

        r = resolve_readme(row(), cand(default_branch="dev"),
                           http_get=fake_get)
        self.assertEqual(r["state"], "ok")
        self.assertIn("dev", r["source"])

    def test_remote_all_404_is_none_state(self):
        r = resolve_readme(row(), cand(),
                           http_get=lambda u: FakeResp(404))
        self.assertEqual(r["state"], "none")
        self.assertIn("public repos", r["message"])

    def test_network_error_is_none_state_not_exception(self):
        def boom(url):
            raise OSError("no route")

        r = resolve_readme(row(), cand(), http_get=boom)
        self.assertEqual(r["state"], "none")


class TestRenderAndLookup(unittest.TestCase):
    def test_sanitiser_strips_script_and_handlers(self):
        html_out = render_markdown(
            '# Hi\n\n<script>alert(1)</script>\n\n'
            '<a href="https://x" onclick="evil()">x</a>\n'
        )
        self.assertNotIn("<script", html_out)
        self.assertNotIn("onclick", html_out)
        self.assertIn("<h1>Hi</h1>", html_out)

    def test_candidate_for_row(self):
        cands = [cand(), cand(full_name="justin/other", name="other")]
        self.assertIs(candidate_for_row(row(), cands), cands[0])
        self.assertIsNone(candidate_for_row(row(github_repo=""), cands))
        self.assertIsNone(candidate_for_row(row(github_repo="a/b"), cands))


if __name__ == "__main__":
    unittest.main()
