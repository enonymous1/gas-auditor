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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..pipeline import ScanOptions, run_scan

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
        """A copy of the current scan state (status, rows, timestamps,
        error). Copying under the lock means callers -- HTTP handlers
        polling mid-scan -- never observe a half-updated state."""
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
    """Build the real scan callable around the shared pipeline
    (pipeline.run_scan -- the same sequence the CLI runs, so a dashboard
    scan and a CLI run can never disagree about what a scan means).
    Auth happens inside the callable (i.e. on Scan-click, on the worker
    thread) -- importing or starting the web app needs no credentials.
    GitHub enrichment is opt-in, exactly like the CLI: pass a candidates
    source (JSON inventory or checkout directory) and/or a mapping file."""

    options = ScanOptions(
        credentials_path=credentials_path,
        token_path=token_path,
        metrics_granularity=metrics_granularity,
        process_limit=process_limit,
        process_since_days=process_since_days,
        all_drives=all_drives,
        github_candidates_path=github_candidates_path,
        github_mapping_path=github_mapping_path,
        state_path=state_path,
        script_ids=list(script_ids or []),
        script_ids_file=script_ids_file,
        script_ids_out=script_ids_out,
    )

    def run() -> list[dict[str, Any]]:
        """Execute one scan on the calling thread via the shared pipeline."""
        return run_scan(options)

    return run
