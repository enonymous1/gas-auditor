"""Project discovery via Google Drive API v3.

A Drive file with mimeType 'application/vnd.google-apps.script' *is* an
Apps Script project, and its Drive file ID is its Script ID.

IMPORTANT LIMITATION (Google platform rule, verified against Google's
docs and live behaviour, Oct 2026): container-bound scripts (created from
inside a Sheet/Doc/Slides/Form) "do not appear in Google Drive" -- they
are ghosted from files.list entirely, and the container file carries no
reference back to its script. No API can enumerate them. They ARE
fetchable by files.get when the scriptId is known, so discovery accepts
`extra_ids`: hand the auditor the bound projects' IDs once (from their
script-editor URLs) and the tracking state remembers them -- the CLI and
dashboard pass every state-known ID back in on later runs, so seeded
projects are re-fetched and fully audited forever after.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .config import SCRIPT_MIMETYPE
from .retry import execute_with_retry

log = logging.getLogger(__name__)

_FILE_FIELDS = (
    "id, name, mimeType, createdTime, modifiedTime, "
    "description, webViewLink, parents, owners(emailAddress), "
    "lastModifyingUser(emailAddress)"
)


def read_script_ids(path: Path) -> list[str]:
    """Parse a script-IDs file: one ID per line; blank lines ignored and
    '#' starts a comment (whole-line or trailing), so generated files
    with annotated entries round-trip."""
    ids: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        token = line.split("#", 1)[0].strip()
        if token:
            ids.append(token)
    return ids


def format_script_ids(
    rows: Sequence[Mapping[str, Any]],
    extra_ids: Iterable[str] = (),
) -> str:
    """Render an editable script-IDs file from audit rows: every known
    project ID, annotated with its name (and container, when bound).
    `extra_ids` the caller wants preserved (e.g. seeds that didn't
    resolve this run) are appended so editing never loses them."""
    lines = [
        "# Apps Script project IDs -- one per line; '#' starts a comment.",
        "# Standalone projects are found automatically by Drive listing;",
        "# the IDs that matter here are CONTAINER-BOUND projects (created",
        "# from inside a Sheet/Doc/Slides/Form), which Google hides from",
        "# Drive listing. Add a missing bound project's ID -- from its",
        "# script-editor URL: script.google.com/home/projects/<ID>/edit --",
        "# and it will be audited on every run from then on.",
        "",
    ]
    seen: set[str] = set()
    for row in rows:
        sid = str(row.get("script_id") or "")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        name = str(row.get("project_name") or "(unnamed)")
        parent = str(row.get("parent_id") or "")
        note = f"# {name}" + (f"  [bound to {parent}]" if parent else "")
        lines += [note, sid]
    kept = [i for i in extra_ids if i and i not in seen]
    if kept:
        lines += ["", "# Kept from your input (not resolved this run):"]
        lines += kept
    return "\n".join(lines) + "\n"


def fetch_file_meta(drive: Any, file_id: str) -> dict[str, Any] | None:
    """files.get for one ID (works for container-bound scripts, which
    files.list hides). Returns None when the file can't be fetched
    (deleted, or not visible to this account) -- logged, never fatal."""
    try:
        return execute_with_retry(
            drive.files().get(
                fileId=file_id, fields=_FILE_FIELDS, supportsAllDrives=True
            )
        )
    except Exception as exc:  # noqa: BLE001 -- seeded IDs must not abort a run
        log.warning("Could not fetch file %s (%s); skipping it.", file_id, exc)
        return None


def discover_projects(
    drive: Any,
    *,
    all_drives: bool = False,
    extra_ids: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Page through Drive files.list for every Apps Script project, then
    merge in any `extra_ids` not already listed (container-bound seeds /
    state-known IDs), fetched individually via files.get.

    Returns raw Drive file dicts (id == the project's Script ID).
    """
    query = f"mimeType = '{SCRIPT_MIMETYPE}' and trashed = false"
    fields = (
        "nextPageToken, files(id, name, mimeType, createdTime, modifiedTime, "
        "description, webViewLink, parents, owners(emailAddress), "
        "lastModifyingUser(emailAddress))"
    )
    kwargs: dict[str, Any] = {}
    if all_drives:
        # Required trio to see shared-drive content at all; without it,
        # files.list silently returns only 'My Drive'.
        kwargs = {
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
            "corpora": "allDrives",
        }

    projects: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        resp = execute_with_retry(
            drive.files().list(
                q=query,
                fields=fields,
                pageSize=1000,  # Drive v3 max for files.list
                orderBy="modifiedTime desc",
                pageToken=page_token,
                **kwargs,
            )
        )
        projects.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    seen = {p["id"] for p in projects}
    seeded = 0
    for file_id in extra_ids:
        if not file_id or file_id in seen:
            continue
        meta = fetch_file_meta(drive, file_id)
        if meta is not None:
            meta["_seeded"] = True
            projects.append(meta)
            seen.add(file_id)
            seeded += 1
    if seeded:
        log.info("Added %d project(s) by direct ID fetch (bound/seeded).", seeded)
    return projects
