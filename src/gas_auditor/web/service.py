"""Background scan execution for the dashboard.

Why background: a scan is N projects x 4 Google API calls and can run for
minutes. Running it synchronously inside the /api/scan request would hang
the HTMX request (and the server worker) the whole time. Instead the route
starts a daemon thread here and returns immediately; the browser polls
/api/scan/status until the job lands.

The scan itself is injected as a zero-arg callable returning audit rows,
so tests (and other front-ends) never need real Google credentials.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..audit import audit_project
from ..auth import build_services, get_credentials
from ..discovery import discover_projects, format_script_ids, read_script_ids
from ..github_link import enrich_rows, load_candidates, load_mapping
from ..tracking import (
    apply_state,
    describe_changes,
    load_state,
    save_state,
    update_state,
)

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class ScanState:
    status: str = "idle"  # idle | running | done | error
    rows: list[dict[str, Any]] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    error: str = ""


class ScanService:
    """Runs one scan at a time on a background thread; holds the last result."""

    def __init__(self, run_scan: Callable[[], list[dict[str, Any]]]) -> None:
        self._run_scan = run_scan
        self._lock = threading.Lock()
        self._state = ScanState()

    def start(self) -> bool:
        """Start a scan if none is running. Returns False if one already is
        (the caller then just keeps polling the in-flight job)."""
        with self._lock:
            if self._state.status == "running":
                return False
            self._state = ScanState(status="running", started_at=_now())
        threading.Thread(target=self._work, daemon=True).start()
        return True

    def _work(self) -> None:
        try:
            rows = self._run_scan()
        except Exception as exc:  # noqa: BLE001 -- surfaced in the UI fragment
            with self._lock:
                self._state.status = "error"
                self._state.error = f"{type(exc).__name__}: {exc}"
                self._state.finished_at = _now()
            return
        with self._lock:
            self._state.status = "done"
            self._state.rows = rows
            self._state.finished_at = _now()

    def snapshot(self) -> ScanState:
        with self._lock:
            return ScanState(
                status=self._state.status,
                rows=list(self._state.rows),
                started_at=self._state.started_at,
                finished_at=self._state.finished_at,
                error=self._state.error,
            )


def make_default_runner(
    *,
    credentials_path: Path,
    token_path: Path,
    metrics_granularity: str = "WEEKLY",
    process_limit: int = 50,
    process_since_days: int | None = None,
    all_drives: bool = False,
    github_candidates_path: Path | None = None,
    github_mapping_path: Path | None = None,
    state_path: Path | None = Path("gas_audit_state.json"),
    script_ids: list[str] | None = None,
    script_ids_file: Path | None = None,
    script_ids_out: Path | None = None,
) -> Callable[[], list[dict[str, Any]]]:
    """Build the real scan callable from the existing core modules.
    Auth happens inside the callable (i.e. on Scan-click, on the worker
    thread) -- importing or starting the web app needs no credentials.
    GitHub enrichment is opt-in, exactly like the CLI: pass a candidates
    source (JSON inventory or checkout directory) and/or a mapping file."""

    def run() -> list[dict[str, Any]]:
        creds = get_credentials(credentials_path, token_path)
        drive, script = build_services(creds)
        # State-known IDs seed discovery (container-bound projects are
        # invisible to Drive listing; see discovery.py). Loaded once here
        # and reused for the post-scan tracking update below.
        state = load_state(state_path) if state_path is not None else None
        file_ids = read_script_ids(script_ids_file) if script_ids_file else []
        seed_ids: list[str] = list(script_ids or []) + file_ids
        if state is not None:
            seed_ids.extend(state.get("projects", {}).keys())
        drive_files = discover_projects(
            drive, all_drives=all_drives, extra_ids=seed_ids
        )
        rows = [
            audit_project(
                f, script,
                metrics_granularity=metrics_granularity,
                process_limit=process_limit,
                process_since_days=process_since_days,
            )
            for f in drive_files
        ]
        if github_candidates_path or github_mapping_path:
            candidates = (
                load_candidates(github_candidates_path)
                if github_candidates_path else []
            )
            mapping = load_mapping(github_mapping_path) if github_mapping_path else {}
            explicit = {f["id"]: f.get("description") or "" for f in drive_files}
            enrich_rows(rows, candidates, mapping, explicit)
        if state is not None:
            # Same cross-run tracking as the CLI, sharing its state file.
            changes = update_state(
                state, rows,
                scope="all_drives" if all_drives else "my_drive",
            )
            apply_state(rows, state)
            save_state(state_path, state)
            for line in describe_changes(changes):
                log.info(line)
        if script_ids_out is not None:
            script_ids_out.write_text(
                format_script_ids(rows, extra_ids=file_ids), encoding="utf-8"
            )
        return rows

    return run
