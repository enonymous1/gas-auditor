"""processes.listScriptProcesses: recent executions for one project.

NOTE: there is NO Apps Script API endpoint that lists installable triggers.
This is the closest signal -- a TIME_DRIVEN / TRIGGER processType tells you
a trigger fired, not how it is configured.

In the Python client the filter arguments are the flattened names
scriptProcessFilter_types / _statuses / _startTime etc., and each returned
Process uses the keys processType / processStatus (not type / status).
Process types include TIME_DRIVEN, TRIGGER, WEBAPP, EDITOR, EXECUTION_API,
ADD_ON, SIMPLE_TRIGGER, MENU, BATCH_TASK. Statuses include COMPLETED,
FAILED, TIMED_OUT, RUNNING, CANCELED, PAUSED, DELAYED.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from .retry import execute_with_retry


def summarise_processes(processes: list[dict[str, Any]]) -> dict[str, Any]:
    """Break down Process objects by type/status and find the latest run."""
    types = Counter(p.get("processType", "UNKNOWN") for p in processes)
    statuses = Counter(p.get("processStatus", "UNKNOWN") for p in processes)
    failed = statuses.get("FAILED", 0) + statuses.get("TIMED_OUT", 0)

    last: dict[str, Any] = {}
    if processes:
        # RFC 3339 timestamps sort correctly as plain strings.
        last = max(processes, key=lambda p: p.get("startTime", ""))

    return {
        "recent_process_count": len(processes),
        "process_types": dict(types),
        "process_statuses": dict(statuses),
        "failed_process_count": failed,
        "last_execution_time": last.get("startTime", ""),
        "last_execution_type": last.get("processType", ""),
        "last_execution_status": last.get("processStatus", ""),
        "last_execution_function": last.get("functionName", ""),
    }


def fetch_processes(
    script: Any,
    script_id: str,
    *,
    limit: int = 50,
    since_days: int | None = None,
) -> dict[str, Any]:
    """Fetch up to `limit` most recent processes for one project, paging as
    needed. Optionally restrict to the last `since_days` days via the
    (flattened) scriptProcessFilter_startTime argument."""
    extra: dict[str, Any] = {}
    if since_days:
        start = datetime.now(timezone.utc) - timedelta(days=since_days)
        extra["scriptProcessFilter_startTime"] = start.strftime("%Y-%m-%dT%H:%M:%SZ")

    processes: list[dict[str, Any]] = []
    page_token: str | None = None
    while len(processes) < limit:
        resp = execute_with_retry(
            script.processes().listScriptProcesses(
                scriptId=script_id,
                pageSize=min(50, limit - len(processes)),
                pageToken=page_token,
                **extra,
            )
        )
        processes.extend(resp.get("processes", []) or [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return summarise_processes(processes[:limit])
