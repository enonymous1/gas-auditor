"""View-model tests: pure display logic, no Flask, no server."""

import unittest

from gas_auditor.web.viewmodels import (
    fmt_time,
    project_detail,
    results_view,
    row_view,
    status_view,
)

from web_fixtures import FAKE_ROW


class TestFmtTime(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(fmt_time("2026-10-20T17:20:00Z"), "2026-10-20 17:20")
        self.assertEqual(fmt_time(""), "—")


class TestStatusView(unittest.TestCase):
    def test_ok(self):
        v = status_view(FAKE_ROW)
        self.assertEqual(v["kind"], "ok")
        self.assertIn("COMPLETED", v["text"])

    def test_failed_flagged(self):
        v = status_view({**FAKE_ROW, "last_execution_status": "FAILED",
                         "failed_process_count": 2})
        self.assertEqual(v["kind"], "fail")
        self.assertIn("2 failed in sample", v["text"])

    def test_processes_error_is_unknown_not_ok(self):
        v = status_view({**FAKE_ROW, "processes_error": "HttpError 403: no"})
        self.assertEqual(v["kind"], "unknown")

    def test_no_executions(self):
        v = status_view({**FAKE_ROW, "last_execution_status": ""})
        self.assertEqual(v["kind"], "none")


class TestRowView(unittest.TestCase):
    def test_row(self):
        v = row_view(FAKE_ROW)
        self.assertEqual(v["name"], "My Script")
        self.assertEqual(v["modified"], "2026-10-20 17:20")
        self.assertEqual(v["file_count"], 3)
        self.assertEqual(v["scope_count"], 1)
        self.assertEqual(v["scopes"][0]["short"], "spreadsheets.readonly")
        self.assertTrue(v["scopes"][0]["known"])


class TestResultsView(unittest.TestCase):
    def test_summary_counts_errors(self):
        rows = [FAKE_ROW, {**FAKE_ROW, "metrics_error": "boom"}]
        v = results_view(rows, finished_at="2026-10-20T18:00:00Z")
        self.assertIn("2 project(s)", v["summary"])
        self.assertIn("1 with stage errors", v["summary"])
        self.assertEqual(len(v["rows"]), 2)


class TestProjectDetail(unittest.TestCase):
    def _rich(self):
        from fixtures import DRIVE_FILE, FakeScript

        from gas_auditor import audit_project

        return audit_project(
            DRIVE_FILE, FakeScript(),
            metrics_granularity="WEEKLY",
            process_limit=50, process_since_days=None,
        )

    def _flat(self, detail):
        return {
            label: value
            for g in detail["groups"] for label, value in g["items"]
        }

    def test_groups_cover_the_row(self):
        rich = self._rich()
        d = project_detail(rich)
        flat = self._flat(d)
        self.assertEqual(flat["Project name"], "T")
        self.assertEqual(flat["Type"], "Container-bound")
        self.assertEqual(flat["Files by type"], "SERVER_JS=1; HTML=1; JSON=1")
        self.assertEqual(flat["Function names"], "a; b")
        self.assertIn("script.google.com/home/projects/ABC/edit",
                      d["editor_link"])
        self.assertEqual(d["drive_link"], rich["web_view_link"])
        self.assertEqual(d["errors"], [])

    def test_github_block_states(self):
        rich = self._rich()
        unchecked = project_detail(dict(rich))
        self.assertFalse(unchecked["github"]["checked"])

        linked = project_detail(dict(
            rich, github_repo="justin/x",
            github_repo_url="https://github.com/justin/x",
            github_match="probable", github_evidence="name match"))
        self.assertEqual(linked["github"]["repo"], "justin/x")
        self.assertEqual(linked["github"]["kind"], "ok")

        searched_none = project_detail(dict(rich, github_match="none"))
        self.assertTrue(searched_none["github"]["checked"])
        self.assertEqual(searched_none["github"]["repo"], "")

    def test_stage_errors_listed(self):
        d = project_detail(dict(self._rich(), metrics_error="HttpError 403"))
        self.assertEqual(d["errors"], [("metrics_error", "HttpError 403")])


if __name__ == "__main__":
    unittest.main()
