"""Render the Flask dashboard as a static site for GitHub Pages.

What it does: builds the real Flask app (create_app) with a ScanService
pre-loaded with seeded demo rows, renders every page through Flask's
test client -- the same Jinja templates the live dashboard serves --
and writes static HTML files. No Google credentials, no token, no state
file: the demo data lives in this file, and the script takes no
--credentials / --state / --script-ids arguments at all, so real account
data cannot be frozen by accident.

What the frozen site is and is not: it is browsable and click-through
(inventory table -> project detail pages -> scope definitions), and the
theme toggle still works (localStorage + CSS only). It is NOT the app:
the Scan button is disabled (it must not pretend to scan), the CSV and
script-IDs downloads are pre-generated files, scope chips link to a
pre-rendered scopes page instead of a modal, and the README lazy-load
becomes a static note. A banner on every page says exactly that.

Links are relative (project-<id>.html, index.html, gas_audit.csv), never
root-relative, so the site works under a GitHub Pages project subpath
(https://<user>.github.io/gas-auditor/) as well as at a domain root.

Usage (from the repo root, with the web extra installed):

    python scripts/freeze.py --output freeze-site

`freeze-site/` is gitignored -- the Pages workflow builds it in CI and
uploads it; it is never committed.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import unquote

# The script runs from the repo root without an install, so the src
# layout needs to be on the path before the package imports below.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gas_auditor.audit import _blank_row  # noqa: E402,SLF001 -- same codebase
from gas_auditor.discovery import format_script_ids  # noqa: E402
from gas_auditor.output import render_csv  # noqa: E402
from gas_auditor.web.app import create_app  # noqa: E402
from gas_auditor.web.scopes import scope_view  # noqa: E402
from gas_auditor.web.service import ScanService  # noqa: E402

# Real scope URLs (the curated definitions in web/scopes.py cover these,
# so the frozen scopes page shows real definitions, not "unknown" notes).
SCOPE_DRIVE_META = "https://www.googleapis.com/auth/drive.metadata.readonly"
SCOPE_PROJECTS = "https://www.googleapis.com/auth/script.projects.readonly"
SCOPE_METRICS = "https://www.googleapis.com/auth/script.metrics"
SCOPE_PROCESSES = "https://www.googleapis.com/auth/script.processes"
SCOPE_SHEETS = "https://www.googleapis.com/auth/spreadsheets.readonly"
SCOPE_GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send"

BANNER = (
    '<div style="border:2px dashed var(--border); border-radius:6px; '
    "padding:0.75rem 1rem; margin:0 0 1rem 0;\">"
    "<strong>Static demo.</strong> This page was rendered from seeded demo "
    "data (invented projects, not a real account). Scan is disabled, and "
    "the CSV / script-IDs downloads below are pre-generated files. "
    "Run <code>gas-audit-web</code> locally for the live dashboard."
    "</div>"
)

README_NOTE = (
    "<p><small>README preview is disabled in this static demo.</small></p>"
)

HTMX_SCRIPT = (
    '<script src="https://unpkg.com/htmx.org@2/dist/htmx.min.js"></script>'
)


def _row(**values):
    """A demo row: every AUDIT_FIELD present (via _blank_row, so the
    schema can't drift from the real audit), with demo values layered
    on top. Names, IDs, and emails are invented -- nothing real."""
    row = _blank_row()
    row.update(values)
    return row


def demo_rows():
    """Six invented projects covering the shapes a visitor should see:
    standalone, container-bound, one with a stage error, one with a
    failed project fetch, every GitHub tier (confirmed / probable /
    none), and a quiet project with no recent executions."""
    return [
        _row(
            project_name="Demo Sheet Helper",
            script_id="demo-sheet-helper-001",
            drive_modified_time="2026-10-28T14:02:00Z",
            drive_created_time="2024-03-11T09:00:00Z",
            parent_id="demo-parent-sheet-001",
            creator_email="demo@example.invalid",
            last_modify_user_email="demo@example.invalid",
            project_create_time="2024-03-11T09:00:00Z",
            project_update_time="2026-10-28T14:02:00Z",
            file_count=4, file_counts_by_type={"SERVER_JS": 2, "HTML": 1, "JSON": 1},
            server_js_count=2, html_count=1, json_count=1,
            function_count=6,
            function_names=["onEdit", "syncRows", "sendSummary", "formatHeader",
                            "archiveOld", "checkQuota"],
            total_source_chars=8420,
            oauth_scopes=[SCOPE_SHEETS, SCOPE_DRIVE_META],
            oauth_scope_count=2,
            advanced_services=["Sheets (serviceId=sheets, v4)"],
            manifest_time_zone="America/New_York", runtime_version="V8",
            has_webapp=False, has_execution_api=False,
            metrics_granularity="WEEKLY", active_users_latest=3,
            total_executions=128, failed_executions=0,
            recent_process_count=12,
            process_types={"TIME_DRIVEN": 12}, process_statuses={"COMPLETED": 12},
            failed_process_count=0,
            last_execution_time="2026-10-28T13:00:00Z",
            last_execution_type="TIME_DRIVEN",
            last_execution_status="COMPLETED",
            last_execution_function="syncRows",
            first_seen="2024-03-12T00:00:00Z", last_seen="2026-10-28T00:00:00Z",
            github_repo="demo-org/demo-sheet-helper", github_repo_url="",
            github_match="confirmed",
            github_evidence="curated mapping override",
        ),
        _row(
            project_name="Demo Standalone Tool",
            script_id="demo-standalone-tool-002",
            drive_modified_time="2026-10-27T18:41:00Z",
            drive_created_time="2023-11-02T10:00:00Z",
            creator_email="demo@example.invalid",
            last_modify_user_email="demo@example.invalid",
            project_create_time="2023-11-02T10:00:00Z",
            project_update_time="2026-10-27T18:41:00Z",
            file_count=9, file_counts_by_type={"SERVER_JS": 6, "HTML": 2, "JSON": 1},
            server_js_count=6, html_count=2, json_count=1,
            function_count=14,
            function_names=["doGet", "doPost", "handleWebhook", "buildReport",
                            "exportCsv", "notifySlack", "cleanup", "migrate",
                            "backfill", "validate", "render", "cacheGet",
                            "cachePut", "logEvent"],
            total_source_chars=31200,
            oauth_scopes=[SCOPE_DRIVE_META, SCOPE_PROJECTS, SCOPE_METRICS,
                          SCOPE_PROCESSES, SCOPE_GMAIL_SEND],
            oauth_scope_count=5,
            advanced_services=["Drive (serviceId=drive, v2)",
                               "Gmail (serviceId=gmail, v1)"],
            manifest_time_zone="America/New_York", runtime_version="V8",
            has_webapp=True, has_execution_api=True,
            metrics_granularity="WEEKLY", active_users_latest=41,
            total_executions=1204, failed_executions=3,
            recent_process_count=50,
            process_types={"WEBAPP": 31, "TIME_DRIVEN": 12, "TRIGGER": 7},
            process_statuses={"COMPLETED": 46, "FAILED": 3, "TIMED_OUT": 1},
            failed_process_count=4,
            last_execution_time="2026-10-27T18:30:00Z",
            last_execution_type="WEBAPP",
            last_execution_status="FAILED",
            last_execution_function="handleWebhook",
            first_seen="2023-11-03T00:00:00Z", last_seen="2026-10-27T00:00:00Z",
            github_repo="demo-org/demo-standalone-tool", github_repo_url="",
            github_match="probable",
            github_evidence="exact name match; contains appsscript.json; "
                            "9/14 functions overlap",
            processes_error="HttpError 429: Quota exceeded (sampled processes "
                            "truncated -- see processes docs)",
        ),
        _row(
            project_name="Demo Bound Script",
            script_id="demo-bound-script-003",
            drive_modified_time="2026-10-20T08:15:00Z",
            drive_created_time="2025-01-19T12:00:00Z",
            parent_id="demo-parent-doc-003",
            creator_email="demo@example.invalid",
            last_modify_user_email="demo@example.invalid",
            project_create_time="2025-01-19T12:00:00Z",
            project_update_time="2026-10-20T08:15:00Z",
            file_count=3, file_counts_by_type={"SERVER_JS": 2, "JSON": 1},
            server_js_count=2, html_count=0, json_count=1,
            function_count=2, function_names=["onOpen", "insertSidebar"],
            total_source_chars=1980,
            oauth_scopes=[SCOPE_DRIVE_META], oauth_scope_count=1,
            advanced_services=[],
            manifest_time_zone="America/New_York", runtime_version="V8",
            has_webapp=False, has_execution_api=False,
            metrics_granularity="WEEKLY", active_users_latest=1,
            total_executions=0, failed_executions=0,
            recent_process_count=2,
            process_types={"SIMPLE_TRIGGER": 2},
            process_statuses={"COMPLETED": 2}, failed_process_count=0,
            last_execution_time="2026-10-20T08:00:00Z",
            last_execution_type="SIMPLE_TRIGGER",
            last_execution_status="COMPLETED",
            last_execution_function="onOpen",
            first_seen="2025-01-20T00:00:00Z", last_seen="2026-10-20T00:00:00Z",
            github_match="none",
            github_evidence="searched, no evidence",
        ),
        _row(
            project_name="Demo Quiet Add-on",
            script_id="demo-quiet-addon-004",
            drive_modified_time="2025-06-01T00:00:00Z",
            drive_created_time="2022-05-05T00:00:00Z",
            creator_email="demo@example.invalid",
            last_modify_user_email="demo@example.invalid",
            project_create_time="2022-05-05T00:00:00Z",
            project_update_time="2025-06-01T00:00:00Z",
            file_count=5, file_counts_by_type={"SERVER_JS": 3, "HTML": 1, "JSON": 1},
            server_js_count=3, html_count=1, json_count=1,
            function_count=4,
            function_names=["onInstall", "onOpen", "showPanel", "refresh"],
            total_source_chars=5100,
            oauth_scopes=[SCOPE_PROJECTS, SCOPE_METRICS], oauth_scope_count=2,
            advanced_services=[],
            manifest_time_zone="UTC", runtime_version="V8",
            has_webapp=False, has_execution_api=False,
            metrics_granularity="WEEKLY", active_users_latest=0,
            total_executions=0, failed_executions=0,
            recent_process_count=0, process_types={}, process_statuses={},
            failed_process_count=0,
            first_seen="2022-05-06T00:00:00Z", last_seen="2025-06-01T00:00:00Z",
            github_match="",
        ),
        _row(
            project_name="Demo Failing Project",
            script_id="demo-failing-project-005",
            drive_modified_time="2026-09-15T11:00:00Z",
            drive_created_time="2024-08-08T00:00:00Z",
            creator_email="demo@example.invalid",
            last_modify_user_email="demo@example.invalid",
            project_create_time="2024-08-08T00:00:00Z",
            project_update_time="2026-09-15T11:00:00Z",
            file_count=0, file_counts_by_type={},
            server_js_count=0, html_count=0, json_count=0,
            function_count=0, function_names=[], total_source_chars=0,
            oauth_scopes=[], oauth_scope_count=0, advanced_services=[],
            metrics_granularity="WEEKLY", active_users_latest=0,
            total_executions=0, failed_executions=0,
            recent_process_count=0, process_types={}, process_statuses={},
            failed_process_count=0,
            first_seen="2024-08-09T00:00:00Z", last_seen="2026-09-15T00:00:00Z",
            github_match="",
            project_error="HttpError 403: The caller does not have permission",
            content_error="HttpError 403: The caller does not have permission",
            metrics_error="HttpError 403: The caller does not have permission",
            processes_error="HttpError 403: The caller does not have permission",
        ),
        _row(
            project_name="Demo Docs Automator",
            script_id="demo-docs-automator-006",
            drive_modified_time="2026-10-29T09:30:00Z",
            drive_created_time="2025-04-14T00:00:00Z",
            parent_id="demo-parent-doc-006",
            creator_email="demo@example.invalid",
            last_modify_user_email="demo@example.invalid",
            project_create_time="2025-04-14T00:00:00Z",
            project_update_time="2026-10-29T09:30:00Z",
            file_count=6, file_counts_by_type={"SERVER_JS": 4, "HTML": 1, "JSON": 1},
            server_js_count=4, html_count=1, json_count=1,
            function_count=8,
            function_names=["onOpen", "buildMenu", "generateDoc", "fillTemplate",
                            "sendForReview", "approveDoc", "archiveDoc",
                            "auditTrail"],
            total_source_chars=12400,
            oauth_scopes=[SCOPE_DRIVE_META, SCOPE_PROJECTS, SCOPE_PROCESSES],
            oauth_scope_count=3,
            advanced_services=["Docs (serviceId=docs, v1)"],
            manifest_time_zone="America/New_York", runtime_version="V8",
            has_webapp=False, has_execution_api=False,
            metrics_granularity="WEEKLY", active_users_latest=7,
            total_executions=342, failed_executions=1,
            recent_process_count=20,
            process_types={"TRIGGER": 14, "EDITOR": 6},
            process_statuses={"COMPLETED": 19, "FAILED": 1},
            failed_process_count=1,
            last_execution_time="2026-10-29T09:00:00Z",
            last_execution_type="TRIGGER",
            last_execution_status="COMPLETED",
            last_execution_function="generateDoc",
            first_seen="2025-04-15T00:00:00Z", last_seen="2026-10-29T00:00:00Z",
            github_repo="demo-org/demo-docs-automator", github_repo_url="",
            github_match="probable",
            github_evidence="exact name match; 5/8 functions overlap",
        ),
    ]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "scope"


def _rewrite_common(html: str, scope_pages: dict[str, str]) -> str:
    """Rewrites shared by every frozen page. `scope_pages` maps a scope
    URL to its anchor slug on scopes.html."""

    def _chip(match: re.Match) -> str:
        url = unquote(match.group(1))
        slug = scope_pages.get(url) or _slug(match.group(2))
        return f'<a class="scope-chip" href="scopes.html#{slug}">{match.group(2)}</a>'

    # Scope chips (modal popups live) -> links to the pre-rendered page.
    html = re.sub(
        r'<button type="button" class="scope-chip"\s+'
        r'hx-get="/api/scope\?u=([^"]+)"[^>]*onclick="showModal\(\)">'
        r"([^<]+)</button>",
        _chip, html,
    )
    # No HTMX hooks remain after the rewrites below; drop the CDN script
    # so the frozen site has no live dependency at all.
    html = html.replace(HTMX_SCRIPT, "")
    # Demo banner directly under <body> on every page.
    html = html.replace("<body>", "<body>\n" + BANNER, 1)
    return html


def _rewrite_index(html: str, scope_pages: dict[str, str]) -> str:
    # Scan button (live) -> disabled: it must not pretend to scan.
    html = re.sub(
        r'<button type="button"\s+hx-get="/api/scan".*?</button>',
        '<button type="button" disabled '
        'title="Scanning is disabled in this static demo">'
        "Scan Workspace (disabled in demo)</button>",
        html, flags=re.DOTALL,
    )
    html = re.sub(r'<div id="scan-loading".*?</div>', "", html, flags=re.DOTALL)
    # Downloads become pre-generated files in the same directory.
    html = html.replace('href="/api/script-ids.txt"', 'href="gas_script_ids.txt"')
    html = html.replace('href="/api/export.csv"', 'href="gas_audit.csv"')
    # Project links + Details modal buttons -> static detail pages.
    html = re.sub(r'href="/project/([^"]+)"', r'href="project-\1.html"', html)
    html = re.sub(
        r'<button type="button" class="details-btn"\s+'
        r'hx-get="/api/project/([^"]+)"[^>]*onclick="showModal\(\)">'
        r"Details</button>",
        r'<a class="details-btn" href="project-\1.html">Details</a>',
        html,
    )
    return _rewrite_common(html, scope_pages)


def _rewrite_project(html: str, scope_pages: dict[str, str]) -> str:
    html = html.replace('href="/"', 'href="index.html"')
    # README lazy-load (live fetch) -> static note.
    html = re.sub(
        r'<div hx-get="/api/project/[^"]+/readme"\s+'
        r'hx-trigger="load" hx-swap="innerHTML">\s*'
        r"<p><em>Loading README…</em></p>\s*</div>",
        README_NOTE, html, flags=re.DOTALL,
    )
    # External links that would 404 for invented demo IDs: the script
    # editor link (built from script_id) and any Drive link. The GitHub
    # repo names stay as plain text (demo rows set no repo URL, so the
    # template already renders them unlinked).
    html = re.sub(
        r' · <a href="https://script\.google\.com/home/projects/[^"]+"'
        r' target="_blank" rel="noopener">Open in script editor ↗</a>',
        "", html,
    )
    html = re.sub(
        r' · <a href="[^"]+" target="_blank" rel="noopener">Open in Drive ↗</a>',
        "", html,
    )
    return _rewrite_common(html, scope_pages)


def freeze(output_dir: Path) -> list[str]:
    """Render the frozen site into `output_dir` (recreated from scratch)
    and return the written file names."""
    rows = demo_rows()
    service = ScanService(lambda: rows)
    app = create_app(service=service)
    service.start()
    deadline = time.time() + 10
    while service.snapshot().status != "done" and time.time() < deadline:
        time.sleep(0.05)
    state = service.snapshot()
    if state.status != "done":
        raise RuntimeError(f"Demo scan did not finish (status={state.status})")

    # Scopes page first: chips on every other page link into it.
    scope_urls: list[str] = []
    for row in rows:
        for url in row.get("oauth_scopes") or []:
            if url not in scope_urls:
                scope_urls.append(url)
    scope_pages = {url: _slug(scope_view(url)["short"]) for url in scope_urls}
    with app.test_request_context():
        from flask import render_template, render_template_string

        sections = []
        for url in scope_urls:
            view = scope_view(url)
            sections.append(
                f'<section id="{scope_pages[url]}">'
                + render_template("fragments/scope.html", scope=view)
                + "</section>"
            )
        scopes_html = render_template_string(
            '{% extends "base.html" %}'
            "{% block title %}OAuth scopes — GAS Auditor demo{% endblock %}"
            "{% block content %}"
            '<p><a href="index.html">← Back to inventory</a></p>'
            "<h1>OAuth scopes in this demo</h1>"
            "<p>Curated definitions for every scope the demo projects "
            "request. In the live dashboard these open as modals; here "
            "they are one static page.</p>"
            + "".join(sections)
            + "{% endblock %}"
        )

    output_dir = Path(output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    written: list[str] = []

    client = app.test_client()
    index = client.get("/")
    assert index.status_code == 200, index.status_code
    (output_dir / "index.html").write_text(
        _rewrite_index(index.get_data(as_text=True), scope_pages),
        encoding="utf-8",
    )
    written.append("index.html")

    for row in rows:
        sid = row["script_id"]
        resp = client.get(f"/project/{sid}")
        assert resp.status_code == 200, (sid, resp.status_code)
        (output_dir / f"project-{sid}.html").write_text(
            _rewrite_project(resp.get_data(as_text=True), scope_pages),
            encoding="utf-8",
        )
        written.append(f"project-{sid}.html")

    (output_dir / "scopes.html").write_text(
        _rewrite_common(scopes_html, scope_pages), encoding="utf-8"
    )
    written.append("scopes.html")
    (output_dir / "gas_audit.csv").write_text(
        render_csv(rows), encoding="utf-8"
    )
    written.append("gas_audit.csv")
    (output_dir / "gas_script_ids.txt").write_text(
        format_script_ids(rows), encoding="utf-8"
    )
    written.append("gas_script_ids.txt")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the dashboard as a static demo site "
                    "(seeded demo data only -- no credentials, no state)."
    )
    parser.add_argument("--output", default="freeze-site",
                        help="Output directory (default: freeze-site)")
    args = parser.parse_args(argv)
    written = freeze(Path(args.output))
    print(f"Freeze wrote {len(written)} files to {args.output}:")
    for name in written:
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
