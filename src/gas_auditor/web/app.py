"""Flask application factory and routes for the GAS auditor dashboard.

Templates live in templates/ (Jinja2); all display logic lives in
viewmodels.py, so templates stay declarative and logic stays testable.

Routes
------
GET /                 dashboard page (templates/index.html): header,
                      Scan Workspace button, #inventory-results target,
                      #scan-loading HTMX indicator
GET /api/scan         start a background scan (service.ScanService) and
                      return the self-polling scanning fragment
GET /api/scan/status  while running -> scanning fragment (keeps polling);
                      done -> results fragment (summary + table, polling
                      stops); error -> error fragment
GET /api/export.csv   the last completed scan as a CSV download
                      (409 until a scan has completed) -- the dashboard is
                      an additional surface, the CSV reporting path via the
                      CLI is unchanged
GET /project/<id>     full-page detail for one project of the last scan
GET /api/project/<id> the same detail as a fragment (the table's modal)
GET /api/project/<id>/readme
                      the linked GitHub repo's README, rendered -- from
                      the candidate's local checkout when known, else
                      raw.githubusercontent.com (public repos); loaded
                      lazily by the detail view and cached per scan
GET /api/scope?u=<url> definition fragment for one OAuth scope (modal)

The index page is rendered with the last completed scan's results when
one exists, so navigating back from a project page doesn't force a
re-scan; the Scan button always starts a fresh scan.

Serving: main() uses Flask's built-in development server, which is the
right weight for a local, single-user tool (it prints its own
not-for-production warning; don't expose this beyond localhost -- the
dashboard has no auth of its own).

Flask is an optional dependency: pip install -e ".[web]"
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

try:
    from flask import Flask, Response, render_template, request
except ImportError as exc:  # pragma: no cover -- exercised only without extra
    raise RuntimeError(
        'Flask is not installed. Install the web extra: pip install -e ".[web]"'
    ) from exc

from ..discovery import format_script_ids
from ..github_link import load_candidates
from ..output import render_csv
from .readme import candidate_for_row, resolve_readme
from .scopes import scope_view
from .service import ScanService, make_default_runner
from .viewmodels import project_detail, results_view

log = logging.getLogger(__name__)


def create_app(
    service: ScanService | None = None,
    *,
    github_candidates: list | None = None,
    readme_http_get=None,
    **scan_kwargs,
) -> Flask:
    """Build the Flask app. Pass a ScanService to inject a scan runner
    (tests do); otherwise a real Google-backed runner is built from
    scan_kwargs (credentials_path, token_path, metrics_granularity,
    process_limit, process_since_days, all_drives, github_candidates_path,
    github_mapping_path).

    github_candidates (the github_link candidate list) lets the README
    resolver find local checkouts; when not given but a candidates path is
    among scan_kwargs, it is loaded from there. readme_http_get overrides
    the README remote fetch (tests)."""
    candidates_path = scan_kwargs.get("github_candidates_path")
    if github_candidates is None and candidates_path:
        github_candidates = load_candidates(Path(candidates_path))
    candidates = github_candidates or []

    if service is None:
        credentials = Path(scan_kwargs.pop("credentials_path", "credentials.json"))
        token = Path(scan_kwargs.pop("token_path", "token.json"))
        if scan_kwargs.get("github_candidates_path"):
            scan_kwargs["github_candidates_path"] = Path(
                scan_kwargs["github_candidates_path"]
            )
        if scan_kwargs.get("github_mapping_path"):
            scan_kwargs["github_mapping_path"] = Path(
                scan_kwargs["github_mapping_path"]
            )
        service = ScanService(
            make_default_runner(
                credentials_path=credentials, token_path=token, **scan_kwargs
            )
        )

    app = Flask(__name__)
    readme_cache: dict[str, dict] = {}

    def _find_row(script_id: str):
        state = service.snapshot()
        if state.status != "done":
            return None
        for row in state.rows:
            if row.get("script_id") == script_id:
                return row
        return None

    @app.get("/")
    def index():
        # Render the last scan's state server-side: completed -> results
        # (back-navigation lands on the table, no re-scan), running ->
        # the polling fragment (rejoins the in-flight scan), error ->
        # the error fragment. Only an explicit Scan click starts fresh.
        state = service.snapshot()
        if state.status == "done":
            initial = render_template(
                "fragments/results.html",
                view=results_view(state.rows, finished_at=state.finished_at),
            )
        elif state.status == "running":
            initial = render_template("fragments/scanning.html")
        elif state.status == "error":
            initial = render_template("fragments/error.html", message=state.error)
        else:
            initial = ""
        return render_template("index.html", initial_results=initial)

    @app.get("/api/scope")
    def scope_definition():
        url = request.args.get("u", "")
        if not url:
            return Response("<p>Missing scope URL.</p>", status=400)
        return render_template("fragments/scope.html", scope=scope_view(url))

    @app.get("/api/scan")
    def scan():
        # Idempotent while running: a second click just rejoins the poll.
        service.start()
        return render_template("fragments/scanning.html")

    @app.get("/api/scan/status")
    def scan_status():
        state = service.snapshot()
        if state.status in ("running", "idle"):
            return render_template("fragments/scanning.html")
        if state.status == "error":
            return render_template("fragments/error.html", message=state.error)
        return render_template(
            "fragments/results.html",
            view=results_view(state.rows, finished_at=state.finished_at),
        )

    @app.get("/project/<script_id>")
    def project_page(script_id):
        row = _find_row(script_id)
        if row is None:
            return Response(
                "Unknown project (no completed scan, or id not in it). "
                "Run a scan first, then open the project from the table.",
                status=404, mimetype="text/plain",
            )
        return render_template("project.html", detail=project_detail(row))

    @app.get("/api/project/<script_id>")
    def project_fragment(script_id):
        row = _find_row(script_id)
        if row is None:
            return Response(
                "<p>Unknown project — run a scan first.</p>", status=404
            )
        return render_template(
            "fragments/project_detail.html", detail=project_detail(row)
        )

    @app.get("/api/project/<script_id>/readme")
    def project_readme(script_id):
        row = _find_row(script_id)
        if row is None:
            return Response("<p>Unknown project — run a scan first.</p>",
                            status=404)
        if script_id not in readme_cache:
            readme_cache[script_id] = resolve_readme(
                row,
                candidate_for_row(row, candidates),
                http_get=readme_http_get,
            )
        return render_template(
            "fragments/readme.html",
            readme=readme_cache[script_id],
            repo=row.get("github_repo") or "",
            repo_url=row.get("github_repo_url") or "",
        )

    @app.get("/api/script-ids.txt")
    def script_ids_file() -> Response:
        """Downloadable, editable script-IDs file generated from the last
        scan's rows (plus any IDs remembered in the tracking state) --
        the easy base for adding missing container-bound IDs."""
        ids_state_path = scan_kwargs.get("state_path")
        state_ids: list[str] = []
        if ids_state_path is not None and Path(ids_state_path).exists():
            try:
                saved = json.loads(
                    Path(ids_state_path).read_text(encoding="utf-8")
                )
                state_ids = list(saved.get("projects", {}).keys())
            except (OSError, ValueError):
                state_ids = []
        body = format_script_ids(service.snapshot().rows, extra_ids=state_ids)
        return Response(
            body,
            mimetype="text/plain",
            headers={
                "Content-Disposition": "attachment; filename=gas_script_ids.txt"
            },
        )

    @app.get("/api/export.csv")
    def export_csv():
        state = service.snapshot()
        if state.status != "done":
            return Response(
                "No completed scan yet -- run Scan Workspace first.",
                status=409, mimetype="text/plain",
            )
        return Response(
            render_csv(state.rows),
            mimetype="text/csv",
            headers={"Content-Disposition": 'attachment; filename="gas_audit.csv"'},
        )

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve the GAS auditor Flask dashboard."
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind host (default: 127.0.0.1 -- local only)")
    parser.add_argument("--port", type=int, default=5001,
                        help="Bind port (default: 5001)")
    parser.add_argument("--credentials", default="credentials.json")
    parser.add_argument("--token", default="token.json")
    parser.add_argument("--metrics-granularity", choices=["DAILY", "WEEKLY"],
                        default="WEEKLY")
    parser.add_argument("--process-limit", type=int, default=50)
    parser.add_argument("--process-since-days", type=int, default=None)
    parser.add_argument("--all-drives", action="store_true")
    parser.add_argument("--github-candidates", default=None, metavar="PATH",
                        help="Enable GitHub association matching: a JSON "
                             "inventory export or a directory of local repo "
                             "checkouts (also enables README display).")
    parser.add_argument("--github-mapping", default=None, metavar="PATH",
                        help="Curated {scriptId: 'owner/repo'} JSON overrides.")
    parser.add_argument("--state", default="gas_audit_state.json", metavar="PATH",
                        help="Cross-run tracking state file, shared with the "
                             "CLI (default: gas_audit_state.json)")
    parser.add_argument("--no-state", action="store_true",
                        help="Disable cross-run tracking for dashboard scans")
    parser.add_argument("--script-id", action="append", default=[], metavar="ID",
                        help="Also audit this scriptId directly (repeatable) "
                             "-- the way to include container-bound projects.")
    parser.add_argument("--script-ids-file", default=None, metavar="PATH",
                        help="Text file of scriptIds, one per line.")
    parser.add_argument("--script-ids-out", default=None, metavar="PATH",
                        help="After each scan, (over)write this file with "
                             "every known project ID (annotated, editable).")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    app = create_app(
        credentials_path=args.credentials,
        token_path=args.token,
        metrics_granularity=args.metrics_granularity,
        process_limit=args.process_limit,
        process_since_days=args.process_since_days,
        all_drives=args.all_drives,
        github_candidates_path=args.github_candidates,
        github_mapping_path=args.github_mapping,
        state_path=None if args.no_state else Path(args.state),
        script_ids=args.script_id,
        script_ids_file=Path(args.script_ids_file) if args.script_ids_file else None,
        script_ids_out=Path(args.script_ids_out) if args.script_ids_out else None,
    )
    log.info("Dashboard on http://%s:%d (Ctrl+C to stop)", args.host, args.port)
    # threaded=True so /api/scan/status polling stays responsive; the scan
    # itself runs on ScanService's own thread regardless.
    app.run(host=args.host, port=args.port, threaded=True)
    return 0
