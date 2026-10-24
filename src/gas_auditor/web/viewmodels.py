"""View-model preparation for the Jinja templates. Pure functions, no I/O
and no Flask imports: audit rows in, plain display dicts out. All the
presentation decisions (shortened scope names, timestamp formatting,
execution-status wording/colour class) live here so the templates stay
declarative and this logic stays unit-testable without a server.
"""

from __future__ import annotations

from typing import Any

from .scopes import scope_view


def fmt_time(rfc3339: str) -> str:
    """'2026-10-20T17:20:00Z' -> '2026-10-20 17:20' (display only)."""
    if not rfc3339:
        return "—"
    return rfc3339.replace("T", " ")[:16].removesuffix("Z")


def status_view(row: dict[str, Any]) -> dict[str, str]:
    """Recent Execution Status as {kind, text}.

    kind maps to a CSS class in base.html: ok | fail | unknown | none.
    A processes-stage error reads as 'unknown', never as OK.
    """
    if row.get("processes_error"):
        return {"kind": "unknown", "text": "⚠ unknown — processes API error"}
    failed = int(row.get("failed_process_count") or 0)
    status = row.get("last_execution_status") or ""
    when = fmt_time(row.get("last_execution_time") or "")
    if not status:
        return {"kind": "none", "text": "— no recent executions"}
    if status in ("FAILED", "TIMED_OUT") or failed:
        extra = f" ({failed} failed in sample)" if failed else ""
        return {"kind": "fail", "text": f"✗ {status} · {when}{extra}"}
    return {"kind": "ok", "text": f"✓ {status} · {when}"}


def row_view(row: dict[str, Any]) -> dict[str, Any]:
    """Flatten one audit row into exactly what _table.html renders."""
    scopes = row.get("oauth_scopes") or []
    return {
        "name": row.get("project_name") or row.get("script_id") or "(unnamed)",
        "script_id": row.get("script_id") or "",
        "link": row.get("web_view_link") or "",
        "modified": fmt_time(row.get("drive_modified_time") or ""),
        "file_count": int(row.get("file_count") or 0),
        "scope_count": len(scopes),
        # Clickable chips: short name + full URL + definition metadata.
        "scopes": [scope_view(s) for s in scopes],
        "status": status_view(row),
    }


# ---------------------------------------------------------------------------
# Project detail (full page + modal share this view model)
# ---------------------------------------------------------------------------

def _counts(mapping: Any) -> str:
    """{'HTML': 1, 'JSON': 2} -> 'HTML=1; JSON=2' ('—' when empty)."""
    if not isinstance(mapping, dict) or not mapping:
        return "—"
    return "; ".join(f"{k}={v}" for k, v in mapping.items())


def _yesno(value: Any) -> str:
    return "yes" if value else "no"


def _join(values: Any, sep: str = "; ") -> str:
    if isinstance(values, list):
        return sep.join(str(v) for v in values) if values else "—"
    return str(values) if values else "—"


TIER_KIND = {"confirmed": "ok", "probable": "ok", "possible": "unknown",
             "none": "none"}


def project_detail(row: dict[str, Any]) -> dict[str, Any]:
    """Everything the detail partial renders: grouped label/value sections,
    outbound links, the GitHub association block, and any stage errors."""
    sid = row.get("script_id") or ""
    groups: list[dict[str, Any]] = [
        {"title": "Overview", "items": [
            ("Project name", row.get("project_name") or "—"),
            ("Script ID", sid or "—"),
            ("Type", "Container-bound" if row.get("parent_id") else "Standalone"),
            ("Created (Drive)", fmt_time(row.get("drive_created_time") or "")),
            ("Modified (Drive)", fmt_time(row.get("drive_modified_time") or "")),
            ("Creator", row.get("creator_email") or "—"),
            ("Last modifying user", row.get("last_modify_user_email") or "—"),
            ("Project created", fmt_time(row.get("project_create_time") or "")),
            ("Project updated", fmt_time(row.get("project_update_time") or "")),
            ("First seen by auditor", fmt_time(row.get("first_seen") or "")),
            ("Last seen by auditor", fmt_time(row.get("last_seen") or "")),
        ]},
        {"title": "Code & manifest", "items": [
            ("Files", str(int(row.get("file_count") or 0))),
            ("Files by type", _counts(row.get("file_counts_by_type"))),
            ("Server JS / HTML / JSON",
             f"{int(row.get('server_js_count') or 0)} / "
             f"{int(row.get('html_count') or 0)} / "
             f"{int(row.get('json_count') or 0)}"),
            ("Functions", str(int(row.get("function_count") or 0))),
            ("Function names", _join(row.get("function_names"))),
            ("Total source size", f"{int(row.get('total_source_chars') or 0):,} chars"),
            ("Manifest time zone", row.get("manifest_time_zone") or "—"),
            ("Runtime", row.get("runtime_version") or "—"),
            ("Web app deployment", _yesno(row.get("has_webapp"))),
            ("Execution API", _yesno(row.get("has_execution_api"))),
        ]},
        {"title": "Permissions", "items": [
            ("Advanced services", _join(row.get("advanced_services"))),
        ]},
        {"title": f"Usage (metrics, {row.get('metrics_granularity') or '—'} window)",
         "items": [
            ("Active users (latest interval)",
             str(int(row.get("active_users_latest") or 0))),
            ("Total executions", str(int(row.get("total_executions") or 0))),
            ("Failed executions", str(int(row.get("failed_executions") or 0))),
        ]},
        {"title": "Recent executions", "items": [
            ("Sampled processes", str(int(row.get("recent_process_count") or 0))),
            ("By type", _counts(row.get("process_types"))),
            ("By status", _counts(row.get("process_statuses"))),
            ("Failed in sample", str(int(row.get("failed_process_count") or 0))),
            ("Last execution",
             f"{fmt_time(row.get('last_execution_time') or '')} · "
             f"{row.get('last_execution_type') or '—'} · "
             f"{row.get('last_execution_status') or '—'} · "
             f"{row.get('last_execution_function') or '—'}"),
        ]},
    ]

    errors = [
        (stage, row[stage])
        for stage in ("project_error", "content_error", "metrics_error",
                      "processes_error")
        if row.get(stage)
    ]

    match = row.get("github_match") or ""
    github = {
        "checked": bool(match),
        "repo": row.get("github_repo") or "",
        "url": row.get("github_repo_url") or "",
        "match": match,
        "kind": TIER_KIND.get(match, "none"),
        "evidence": row.get("github_evidence") or "",
    }

    return {
        "name": row.get("project_name") or sid or "(unnamed)",
        "script_id": sid,
        "drive_link": row.get("web_view_link") or "",
        "editor_link": (
            f"https://script.google.com/home/projects/{sid}/edit" if sid else ""
        ),
        "status": status_view(row),
        "groups": groups,
        "scopes": [scope_view(s) for s in (row.get("oauth_scopes") or [])],
        "errors": errors,
        "github": github,
    }


def results_view(rows: list[dict[str, Any]], *, finished_at: str = "") -> dict[str, Any]:
    """Everything _results.html needs: summary line + per-row view dicts."""
    errored = sum(
        1 for r in rows
        if r.get("project_error") or r.get("content_error")
        or r.get("metrics_error") or r.get("processes_error")
    )
    bits = [f"{len(rows)} project(s)"]
    if finished_at:
        bits.append(f"scanned {fmt_time(finished_at)} UTC")
    if errored:
        bits.append(f"{errored} with stage errors (see CSV *_error columns)")
    return {"summary": " · ".join(bits), "rows": [row_view(r) for r in rows]}
