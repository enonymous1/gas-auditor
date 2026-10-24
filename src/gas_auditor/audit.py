"""Orchestration: build one audit row per discovered Drive file.

Each API stage (projects.get, getContent, getMetrics, listScriptProcesses)
is isolated: a failure is stored in that stage's *_error column and the rest
of the row still fills in, so one deleted / inaccessible / API-disabled
project never aborts the audit of the remaining projects.
"""

from __future__ import annotations

from typing import Any

from .config import AUDIT_FIELDS
from .content import fetch_content
from .errors import err_str
from .metrics import fetch_metrics
from .processes import fetch_processes
from .project import fetch_project_meta


def _blank_row() -> dict[str, Any]:
    """A row with every AUDIT_FIELD present and correctly typed."""
    row: dict[str, Any] = {field: "" for field in AUDIT_FIELDS}
    row.update(
        {
            "file_count": 0, "file_counts_by_type": {}, "server_js_count": 0,
            "html_count": 0, "json_count": 0, "function_count": 0,
            "function_names": [], "total_source_chars": 0,
            "oauth_scopes": [], "oauth_scope_count": 0, "advanced_services": [],
            "has_webapp": False, "has_execution_api": False,
            "active_users_latest": 0, "total_executions": 0, "failed_executions": 0,
            "recent_process_count": 0, "process_types": {}, "process_statuses": {},
            "failed_process_count": 0,
            "github_repo": "", "github_repo_url": "",
            "github_match": "", "github_evidence": "",
            "first_seen": "", "last_seen": "",
        }
    )
    return row


def audit_project(
    drive_file: dict[str, Any],
    script: Any,
    *,
    metrics_granularity: str,
    process_limit: int,
    process_since_days: int | None,
) -> dict[str, Any]:
    """Build the audit row for one Drive file using the Script service."""
    row = _blank_row()
    row["metrics_granularity"] = metrics_granularity

    script_id = drive_file["id"]
    owners = drive_file.get("owners") or [{}]
    row.update(
        {
            "project_name": drive_file.get("name", ""),
            "script_id": script_id,
            "drive_modified_time": drive_file.get("modifiedTime", ""),
            "drive_created_time": drive_file.get("createdTime", ""),
            "web_view_link": drive_file.get("webViewLink", ""),
            "creator_email": owners[0].get("emailAddress", ""),
            "last_modify_user_email": (drive_file.get("lastModifyingUser") or {}).get(
                "emailAddress", ""
            ),
        }
    )

    # -- projects.get: bound-container + authoritative timestamps --
    try:
        meta = fetch_project_meta(script, script_id)
        row["parent_id"] = meta["parent_id"]
        row["project_create_time"] = meta["project_create_time"]
        row["project_update_time"] = meta["project_update_time"]
        if meta["creator_email"]:
            row["creator_email"] = meta["creator_email"]
        if meta["last_modify_user_email"]:
            row["last_modify_user_email"] = meta["last_modify_user_email"]
        if meta["title"]:
            row["project_name"] = meta["title"]
    except Exception as exc:  # noqa: BLE001 -- per-project isolation is the point
        row["project_error"] = err_str(exc)

    # -- projects.getContent: files + manifest --
    try:
        row.update(fetch_content(script, script_id))
    except Exception as exc:  # noqa: BLE001
        row["content_error"] = err_str(exc)

    # -- projects.getMetrics --
    try:
        row.update(fetch_metrics(script, script_id, metrics_granularity))
    except Exception as exc:  # noqa: BLE001
        row["metrics_error"] = err_str(exc)

    # -- processes.listScriptProcesses --
    try:
        row.update(
            fetch_processes(
                script, script_id,
                limit=process_limit, since_days=process_since_days,
            )
        )
    except Exception as exc:  # noqa: BLE001
        row["processes_error"] = err_str(exc)

    return row
