"""Route tests via Flask's test_client with an injected fake scan.
No Google credentials, no real server. Skipped without the web extra.
"""

import tempfile
import time
import unittest
from pathlib import Path

try:
    from gas_auditor.web.app import create_app
except RuntimeError:  # Flask not installed
    raise unittest.SkipTest("Flask not installed (web extra)")

from gas_auditor.web.service import ScanService

from web_fixtures import FAKE_ROW


def _client(rows=None):
    svc = ScanService(lambda: list(rows if rows is not None else [FAKE_ROW]))
    return create_app(service=svc).test_client()


def _scan_until_table(client, timeout: float = 5.0) -> str:
    client.get("/api/scan")
    deadline = time.time() + timeout
    while time.time() < deadline:
        html = client.get("/api/scan/status").get_data(as_text=True)
        if "<table" in html:
            return html
        time.sleep(0.02)
    raise AssertionError("table never arrived via status polling")


class TestScriptIdsDownload(unittest.TestCase):
    def test_script_ids_txt_from_last_scan(self):
        client = _client()
        _scan_until_table(client)  # runs a scan to completion
        resp = client.get("/api/script-ids.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attachment", resp.headers["Content-Disposition"])
        body = resp.get_data(as_text=True)
        self.assertIn(FAKE_ROW["script_id"], body.split())
        self.assertIn("# " + FAKE_ROW["project_name"], body)


class TestRoutes(unittest.TestCase):
    def test_index(self):
        r = _client().get("/")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("Scan Workspace", html)
        self.assertIn('hx-get="/api/scan"', html)
        self.assertIn('hx-target="#inventory-results"', html)
        self.assertIn('hx-indicator="#scan-loading"', html)
        self.assertIn('id="inventory-results"', html)

    def test_scan_returns_polling_fragment(self):
        r = _client().get("/api/scan")
        self.assertEqual(r.status_code, 200)
        self.assertIn("/api/scan/status", r.get_data(as_text=True))

    def test_full_scan_flow_renders_table(self):
        html = _scan_until_table(_client())
        for col in ("Project Name", "Last Modified", "File Count",
                    "Scopes Requested", "Recent Execution Status"):
            self.assertIn(col, html)
        self.assertIn("My Script", html)
        self.assertIn("spreadsheets.readonly", html)
        self.assertIn("Download CSV", html)
        self.assertIn("/api/export.csv", html)

    def test_export_csv_before_scan_is_409(self):
        r = _client().get("/api/export.csv")
        self.assertEqual(r.status_code, 409)

    def test_export_csv_after_scan(self):
        client = _client()
        _scan_until_table(client)
        r = client.get("/api/export.csv")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r.content_type)
        self.assertIn('filename="gas_audit.csv"',
                      r.headers.get("Content-Disposition", ""))
        body = r.get_data(as_text=True)
        self.assertIn("project_name", body.splitlines()[0])
        self.assertIn("My Script", body)

    def test_table_links_to_detail_page_and_modal(self):
        html = _scan_until_table(_client())
        self.assertIn('href="/project/ABC"', html)
        self.assertIn('hx-get="/api/project/ABC"', html)

    def test_project_page_404_before_scan(self):
        self.assertEqual(_client().get("/project/ABC").status_code, 404)

    def test_project_page_and_modal_fragment(self):
        client = _client()
        _scan_until_table(client)
        page = client.get("/project/ABC")
        self.assertEqual(page.status_code, 200)
        body = page.get_data(as_text=True)
        self.assertIn("My Script", body)
        self.assertIn("Back to inventory", body)
        self.assertIn("GitHub association", body)
        self.assertIn("script.google.com/home/projects/ABC/edit", body)

        frag = client.get("/api/project/ABC")
        self.assertEqual(frag.status_code, 200)
        self.assertIn("Code &amp; manifest", frag.get_data(as_text=True))

        self.assertEqual(client.get("/project/NOPE").status_code, 404)
        self.assertEqual(client.get("/api/project/NOPE").status_code, 404)

    def test_readme_route_local_checkout(self):
        linked = dict(
            FAKE_ROW, script_id="L1", project_name="Linked",
            github_repo="justin/invoice-bot",
            github_repo_url="https://github.com/justin/invoice-bot",
            github_match="confirmed", github_evidence="curated mapping",
        )
        with tempfile.TemporaryDirectory() as td:
            readme = Path(td) / "README.md"
            readme.write_text("# Invoice Bot\n\nRenders **here**.\n")
            cand = {"name": "invoice-bot", "full_name": "justin/invoice-bot",
                    "html_url": "https://github.com/justin/invoice-bot",
                    "local_path": td, "readme_path": str(readme),
                    "default_branch": ""}
            svc = ScanService(lambda: [linked])
            client = create_app(service=svc,
                                github_candidates=[cand]).test_client()
            client.get("/api/scan")
            deadline = time.time() + 5
            while time.time() < deadline:
                if client.get("/api/scan/status").status_code == 200 and \
                        "Linked" in client.get("/api/scan/status").get_data(as_text=True):
                    break
                time.sleep(0.02)
            r = client.get("/api/project/L1/readme")
            self.assertEqual(r.status_code, 200)
            body = r.get_data(as_text=True)
            self.assertIn("<h1>Invoice Bot</h1>", body)
            self.assertIn("local checkout", body)

            detail = client.get("/project/L1").get_data(as_text=True)
            self.assertIn("curated mapping", detail)
            self.assertIn("/api/project/L1/readme", detail)

    def test_readme_route_without_github_link(self):
        client = _client()
        _scan_until_table(client)
        r = client.get("/api/project/ABC/readme")
        self.assertEqual(r.status_code, 200)
        self.assertIn("No GitHub association",
                      r.get_data(as_text=True))

    def test_index_shows_cached_results_after_scan(self):
        # Back-navigation case: after a scan completes, a fresh GET /
        # renders the results server-side and does NOT start a new scan.
        calls = {"n": 0}

        def counting_runner():
            calls["n"] += 1
            return [FAKE_ROW]

        svc = ScanService(counting_runner)
        client = create_app(service=svc).test_client()
        _scan_until_table(client)
        self.assertEqual(calls["n"], 1)
        html = client.get("/").get_data(as_text=True)
        self.assertIn("<table", html)
        self.assertIn("My Script", html)
        self.assertIn("Download CSV", html)
        self.assertEqual(calls["n"], 1)  # still one -- no re-scan

    def test_index_before_scan_has_no_table(self):
        html = _client().get("/").get_data(as_text=True)
        self.assertNotIn("<table", html)
        self.assertIn("gas-theme", html)  # theme bootstrap present
        self.assertIn("prefers-color-scheme", html)
        self.assertIn('id="modal"', html)  # shared modal shell

    def test_scope_definition_route(self):
        client = _client()
        url = ("/api/scope?u=https%3A%2F%2Fwww.googleapis.com"
               "%2Fauth%2Fspreadsheets.readonly")
        r = client.get(url)
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn("spreadsheets.readonly", body)
        self.assertIn("Read Google Sheets", body)
        self.assertIn("developers.google.com", body)
        self.assertIn("#sheets", body)

    def test_scope_route_unknown_and_missing(self):
        client = _client()
        r = client.get("/api/scope?u=https%3A%2F%2Fwww.googleapis.com"
                       "%2Fauth%2Fbrand.new.scope")
        self.assertEqual(r.status_code, 200)
        self.assertIn("No curated summary", r.get_data(as_text=True))
        self.assertEqual(client.get("/api/scope").status_code, 400)

    def test_table_renders_scope_chips(self):
        html = _scan_until_table(_client())
        self.assertIn("scope-chip", html)
        self.assertIn("/api/scope?u=", html)
        self.assertIn("showModal()", html)

    def test_error_scan_renders_error_fragment(self):
        def boom():
            raise RuntimeError("no credentials")

        svc = ScanService(boom)
        client = create_app(service=svc).test_client()
        client.get("/api/scan")
        deadline = time.time() + 5
        html = ""
        while time.time() < deadline:
            html = client.get("/api/scan/status").get_data(as_text=True)
            if "Scan failed" in html:
                break
            time.sleep(0.02)
        self.assertIn("Scan failed", html)
        self.assertIn("no credentials", html)


if __name__ == "__main__":
    unittest.main()
