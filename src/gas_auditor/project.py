"""projects.get: authoritative project metadata for one script project.

Kept separate from content/metrics/processes so the orchestration in
audit.py reads as one small function per API stage.
"""

from __future__ import annotations

from typing import Any

from .retry import execute_with_retry


def fetch_project_meta(script: Any, script_id: str) -> dict[str, Any]:
    """Call projects.get and flatten the fields the audit row needs.

    parentId is the Drive ID of the container a bound script is attached to
    (a Doc/Sheet/Form/Slides file); empty for a standalone script.
    """
    meta = execute_with_retry(script.projects().get(scriptId=script_id))
    return {
        "title": meta.get("title", ""),
        "parent_id": meta.get("parentId", ""),
        "project_create_time": meta.get("createTime", ""),
        "project_update_time": meta.get("updateTime", ""),
        "creator_email": (meta.get("creator") or {}).get("emailAddress", ""),
        "last_modify_user_email": (meta.get("lastModifyUser") or {}).get(
            "emailAddress", ""
        ),
    }
