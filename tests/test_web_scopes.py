"""Tests for the curated OAuth scope registry (web/scopes.py)."""

import unittest

try:
    import gas_auditor.web.scopes  # noqa: F401
except RuntimeError:
    raise unittest.SkipTest("web extra not installed")

from gas_auditor.web.scopes import scope_view

P = "https://www.googleapis.com/auth/"


class TestScopeView(unittest.TestCase):
    def test_known_scope(self):
        v = scope_view(P + "drive.metadata.readonly")
        self.assertEqual(v["short"], "drive.metadata.readonly")
        self.assertTrue(v["known"])
        self.assertIn("metadata", v["definition"].lower())
        self.assertEqual(v["sensitivity"], "Restricted")
        self.assertTrue(v["docs_url"].endswith("#drive"))

    def test_auditor_scopes_all_known(self):
        for tail in ("drive.metadata.readonly", "script.projects.readonly",
                     "script.metrics", "script.processes"):
            self.assertTrue(scope_view(P + tail)["known"], tail)

    def test_anchor_mapping(self):
        self.assertTrue(scope_view(P + "spreadsheets")["docs_url"].endswith("#sheets"))
        self.assertTrue(scope_view(P + "gmail.readonly")["docs_url"].endswith("#gmail"))
        self.assertTrue(scope_view(P + "script.projects")["docs_url"].endswith("#script"))
        self.assertTrue(scope_view(P + "userinfo.email")["docs_url"].endswith("#oauth2"))

    def test_unknown_scope_is_honest(self):
        v = scope_view(P + "some.future.scope")
        self.assertFalse(v["known"])
        self.assertEqual(v["sensitivity"], "")
        self.assertIn("No curated summary", v["definition"])
        self.assertIn("oauth2/scopes", v["docs_url"])  # index fallback

    def test_non_google_url_passes_through(self):
        v = scope_view("https://example.invalid/scope")
        self.assertEqual(v["short"], "https://example.invalid/scope")
        self.assertFalse(v["known"])


if __name__ == "__main__":
    unittest.main()
