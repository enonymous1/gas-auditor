"""Cross-run project tracking: first seen / last seen / missing.

A single audit is a snapshot; this module gives the auditor memory across
runs via a small JSON state file (default: gas_audit_state.json). It is
keyed by scriptId (stable across renames/moves) and records, per project:

    project_name   latest title seen
    first_seen     UTC timestamp of the first run that saw it
    last_seen      UTC timestamp of the most recent run that saw it
    times_seen     number of runs that saw it
    status         'active' | 'missing'
    missing_since  first run at which it was absent ('' while active)

Each run reports what changed: new projects, projects that came back,
renames, and projects that went missing (deleted, unshared, or moved out
of the discovery scope -- the file can't tell you which, only that Drive
discovery no longer returns them).

Scope guard: discovery scope matters (--all-drives sees more). If a run's
scope differs from the previous run's, missing-marking is skipped for
that run, so flipping the flag can't mass-flag shared-drive projects.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

STATE_VERSION = 1


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def empty_state() -> dict[str, Any]:
    return {"version": STATE_VERSION, "last_scope": "", "projects": {}}


def load_state(path: Path) -> dict[str, Any]:
    """Load the state file; missing -> empty state. A corrupt file is a
    loud warning and a fresh start (state is a derived cache -- losing it
    only resets first_seen, and silently pretending otherwise is worse)."""
    path = Path(path)
    if not path.exists():
        return empty_state()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or "projects" not in state:
            raise ValueError("unexpected state shape")
        return state
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        log.warning(
            "State file %s is unreadable (%s); starting fresh. "
            "first_seen history is reset.", path, exc,
        )
        return empty_state()


def save_state(path: Path, state: dict[str, Any]) -> None:
    """Atomic write: temp file + replace, so a killed run can't corrupt it."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def update_state(
    state: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    scope: str,
    now: str | None = None,
) -> dict[str, Any]:
    """Fold one run's rows into the state. Returns a changes dict:
    {new: [names], returned: [names], renamed: [(old, new)],
     newly_missing: [records], still_missing: int, scope_changed: bool,
     active: int}. The state dict is mutated in place."""
    now = now or now_iso()
    projects: dict[str, Any] = state.setdefault("projects", {})
    scope_changed = bool(state.get("last_scope")) and state["last_scope"] != scope
    state["last_scope"] = scope

    changes: dict[str, Any] = {
        "new": [], "returned": [], "renamed": [],
        "newly_missing": [], "still_missing": 0,
        "scope_changed": scope_changed, "active": 0,
    }

    seen_ids: set[str] = set()
    for row in rows:
        sid = row.get("script_id") or ""
        if not sid:
            continue
        seen_ids.add(sid)
        name = row.get("project_name") or ""
        rec = projects.get(sid)
        if rec is None:
            projects[sid] = {
                "project_name": name,
                "first_seen": now,
                "last_seen": now,
                "times_seen": 1,
                "status": "active",
                "missing_since": "",
            }
            changes["new"].append(name or sid)
            continue
        if rec.get("status") == "missing":
            changes["returned"].append(name or sid)
        if name and rec.get("project_name") and name != rec["project_name"]:
            changes["renamed"].append((rec["project_name"], name))
        if name:
            rec["project_name"] = name
        rec["last_seen"] = now
        rec["times_seen"] = int(rec.get("times_seen") or 0) + 1
        rec["status"] = "active"
        rec["missing_since"] = ""
    changes["active"] = len(seen_ids)

    for sid, rec in projects.items():
        if sid in seen_ids:
            continue
        if rec.get("status") == "missing":
            changes["still_missing"] += 1
        elif not scope_changed:
            rec["status"] = "missing"
            rec["missing_since"] = now
            changes["newly_missing"].append(rec)
        # scope changed: leave status alone this run (see module docstring)

    return changes


def apply_state(rows: list[dict[str, Any]], state: dict[str, Any]) -> None:
    """Stamp first_seen/last_seen onto each audit row from the state
    (call after update_state so new rows get this run's timestamps)."""
    projects = state.get("projects", {})
    for row in rows:
        rec = projects.get(row.get("script_id") or "")
        if rec:
            row["first_seen"] = rec.get("first_seen", "")
            row["last_seen"] = rec.get("last_seen", "")


def describe_changes(changes: dict[str, Any]) -> list[str]:
    """Human-readable log lines for a changes dict (CLI + dashboard logs)."""
    lines: list[str] = []
    bits = [f"{changes['active']} active"]
    if changes["new"]:
        bits.append(f"{len(changes['new'])} new: {', '.join(changes['new'])}")
    if changes["returned"]:
        bits.append(f"{len(changes['returned'])} returned: "
                    f"{', '.join(changes['returned'])}")
    if changes["renamed"]:
        bits.append("renamed: " + ", ".join(
            f"'{old}' -> '{new}'" for old, new in changes["renamed"]))
    lines.append("Tracking: " + "; ".join(bits) + ".")
    for rec in changes["newly_missing"]:
        lines.append(
            f"Tracking: MISSING since this run: '{rec.get('project_name')}' "
            f"(last seen {rec.get('last_seen')})"
        )
    if changes["still_missing"]:
        lines.append(
            f"Tracking: {changes['still_missing']} previously-missing "
            "project(s) still absent."
        )
    if changes["scope_changed"]:
        lines.append(
            "Tracking: discovery scope changed since last run; "
            "missing-marking skipped for this run."
        )
    return lines
