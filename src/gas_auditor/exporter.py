"""Project exporter: download a project's full source to local folders.

The auditor inspects code; this module *keeps* it -- a bulk, inventory-
driven source archive (clasp does per-project push/pull; this does every
project in your audit list at once, bound projects included, because it
fetches by scriptId via projects.getContent, which Drive listing never
gates).

Layout under the output root, one folder per project:

    <root>/<title-slug>__<scriptId[:8]>/
        Code.js            (SERVER_JS)
        page.html          (HTML)
        appsscript.json    (the JSON file named "appsscript" -- the manifest)
        project.json       (metadata snapshot tying the folder to the audit)

Re-exporting overwrites files in place (a sync-down). Files that exist
locally but are gone upstream are reported as `stale_files`, never
deleted -- an export must not be able to destroy local work.

Note: exported source is your code verbatim; Apps Script projects often
embed API keys or tokens in source. The default output dir is gitignored
in this repo -- keep it that way wherever you point it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .project import fetch_project_meta
from .retry import execute_with_retry

# Apps Script API file types -> local extensions (clasp conventions).
_TYPE_EXT = {"SERVER_JS": ".js", "HTML": ".html", "JSON": ".json"}


def slugify(title: str) -> str:
    """Filesystem-safe folder slug from a project title."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", (title or "").strip())
    slug = re.sub(r"-{2,}", "-", slug).strip("-._")
    return slug or "untitled"


def project_dirname(title: str, script_id: str) -> str:
    """Deterministic per-project folder: title slug + short ID suffix.
    The suffix keeps same-titled projects (e.g. two 'Untitled project')
    in distinct folders and makes the folder traceable to its scriptId."""
    return f"{slugify(title)}__{script_id[:8]}"


def _safe_filename(name: str, ftype: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "file").strip()) or "file"
    ext = _TYPE_EXT.get(ftype, ".txt")
    return base if base.lower().endswith(ext) else base + ext


@dataclass
class ExportResult:
    script_id: str
    title: str = ""
    directory: Path | None = None
    files_written: list[str] = field(default_factory=list)
    stale_files: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def write_project_files(
    meta: dict[str, Any],
    content: dict[str, Any],
    root: Path,
) -> ExportResult:
    """Write one project's files + project.json under `root`. Pure
    filesystem work on already-fetched payloads (offline-testable)."""
    script_id = str(content.get("scriptId") or meta.get("script_id") or "")
    title = str(meta.get("title") or "")
    result = ExportResult(script_id=script_id, title=title)
    target = Path(root) / project_dirname(title, script_id)
    target.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for f in content.get("files", []) or []:
        fname = _safe_filename(str(f.get("name", "")), str(f.get("type", "")))
        (target / fname).write_text(str(f.get("source", "")), encoding="utf-8")
        written.append(fname)

    snapshot = {
        "script_id": script_id,
        "title": title,
        "parent_id": meta.get("parent_id", ""),
        "creator_email": meta.get("creator_email", ""),
        "last_modify_user_email": meta.get("last_modify_user_email", ""),
        "project_create_time": meta.get("project_create_time", ""),
        "project_update_time": meta.get("project_update_time", ""),
        "editor_url": f"https://script.google.com/home/projects/{script_id}/edit",
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": [
            {"name": f.get("name", ""), "type": f.get("type", "")}
            for f in content.get("files", []) or []
        ],
    }
    (target / "project.json").write_text(
        json.dumps(snapshot, indent=2) + "\n", encoding="utf-8"
    )

    on_disk = {
        p.name for p in target.iterdir()
        if p.is_file() and p.name != "project.json"
    }
    result.directory = target
    result.files_written = written
    result.stale_files = sorted(on_disk - set(written))
    return result


def fetch_raw_content(script: Any, script_id: str) -> dict[str, Any]:
    """projects.getContent, raw (content.fetch_content returns only the
    audit summary; export needs the sources themselves)."""
    return execute_with_retry(script.projects().getContent(scriptId=script_id))


def export_project(script: Any, script_id: str, root: Path) -> ExportResult:
    """Fetch + write one project. Errors are captured in the result,
    never raised, so batch exports isolate failures per project."""
    try:
        meta = fetch_project_meta(script, script_id)
        meta["script_id"] = script_id
        content = fetch_raw_content(script, script_id)
        return write_project_files(meta, content, root)
    except Exception as exc:  # noqa: BLE001 -- per-project isolation
        return ExportResult(script_id=script_id, error=f"{type(exc).__name__}: {exc}")


def export_projects(
    script: Any, script_ids: Iterable[str], root: Path
) -> list[ExportResult]:
    """Export many projects (de-duplicated, order preserved)."""
    seen: set[str] = set()
    results: list[ExportResult] = []
    for sid in script_ids:
        if not sid or sid in seen:
            continue
        seen.add(sid)
        results.append(export_project(script, sid, root))
    return results
