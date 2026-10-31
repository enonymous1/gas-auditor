"""The full scan pipeline, shared by the CLI and the Flask dashboard.

Before this module existed, `cli.main()` and
`web.service.make_default_runner()` each carried their own copy of the
same ~60-line sequence: authenticate, load tracking state, build the
seed-ID list, discover, audit every project, optionally enrich with
GitHub matches, update tracking state, write the script-IDs file. The
two copies had already drifted in logging (the CLI logged per-project
progress, the dashboard did not) and any fix to the sequence had to land
twice. This module is the single implementation; both front-ends are
thin shells around it (argument parsing + output for the CLI, a
background thread + HTTP for the dashboard).

The pipeline is deliberately a plain function over a dataclass, not a
class: every input is visible in `ScanOptions`, and tests inject fake
Drive/Script services via `services` instead of needing Google
credentials or monkeypatching the auth module.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .audit import audit_project
from .auth import build_services, get_credentials
from .discovery import discover_projects, format_script_ids, read_script_ids
from .github_link import enrich_rows, load_candidates, load_mapping
from .tracking import (
    apply_state,
    describe_changes,
    load_state,
    save_state,
    update_state,
)

log = logging.getLogger(__name__)

# Progress callback: (index_1based, total, drive_file) -> None. The CLI
# logs "[i/n] name"; the dashboard passes nothing (its UI polls state).
ProgressCallback = Callable[[int, int, dict[str, Any]], None]


@dataclass
class ScanOptions:
    """Everything a scan needs. Defaults match the CLI's flags, so a
    bare `run_scan(ScanOptions(credentials_path=..., token_path=...))`
    behaves like a bare `gas-audit` run."""

    credentials_path: Path
    token_path: Path
    metrics_granularity: str = "WEEKLY"
    process_limit: int = 50
    process_since_days: int | None = None
    all_drives: bool = False
    github_candidates_path: Path | None = None
    github_mapping_path: Path | None = None
    state_path: Path | None = Path("gas_audit_state.json")
    script_ids: list[str] = field(default_factory=list)
    script_ids_file: Path | None = None
    script_ids_out: Path | None = None
    on_project: ProgressCallback | None = None


def run_scan(
    options: ScanOptions,
    *,
    services: tuple[Any, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run one full audit and return the rows.

    `services` is a test seam: pass a (drive, script) pair to skip
    authentication entirely. Production callers leave it unset and the
    pipeline authenticates from `options` (OAuth consent happens here,
    on the calling thread -- which is why the dashboard calls this from
    its background worker, not from a request handler).

    Side effects, in order: the tracking state file is loaded, updated,
    and saved (unless `state_path` is None); the script-IDs file is
    written (when `script_ids_out` is set). CSV writing stays with the
    caller -- the CLI writes it, the dashboard serves it from memory.
    """
    if services is None:
        creds = get_credentials(options.credentials_path, options.token_path)
        drive, script = build_services(creds)
    else:
        drive, script = services

    # Tracking state is loaded BEFORE discovery: its known project IDs
    # double as discovery seeds, so container-bound projects (invisible
    # to Drive listing) stay in the audit once they've ever been seeded.
    state = (
        load_state(options.state_path)
        if options.state_path is not None
        else None
    )

    file_ids = (
        read_script_ids(options.script_ids_file)
        if options.script_ids_file
        else []
    )
    seed_ids: list[str] = list(options.script_ids) + file_ids
    if state is not None:
        seed_ids.extend(state.get("projects", {}).keys())

    log.info("Discovering Apps Script projects in Drive...")
    drive_files = discover_projects(
        drive, all_drives=options.all_drives, extra_ids=seed_ids
    )
    log.info("Found %d project(s). Auditing...", len(drive_files))

    rows = []
    for i, drive_file in enumerate(drive_files, start=1):
        if options.on_project is not None:
            options.on_project(i, len(drive_files), drive_file)
        rows.append(
            audit_project(
                drive_file,
                script,
                metrics_granularity=options.metrics_granularity,
                process_limit=options.process_limit,
                process_since_days=options.process_since_days,
            )
        )

    if options.github_candidates_path or options.github_mapping_path:
        candidates = (
            load_candidates(options.github_candidates_path)
            if options.github_candidates_path
            else []
        )
        mapping = (
            load_mapping(options.github_mapping_path)
            if options.github_mapping_path
            else {}
        )
        # A Drive description naming the repo is a confirmed-tier signal.
        explicit_texts = {
            f["id"]: f.get("description") or "" for f in drive_files
        }
        enrich_rows(rows, candidates, mapping, explicit_texts)
        tiers: dict[str, int] = {}
        for r in rows:
            tiers[r["github_match"]] = tiers.get(r["github_match"], 0) + 1
        log.info(
            "GitHub matching vs %d candidate(s): %s",
            len(candidates),
            ", ".join(f"{k}={tiers[k]}" for k in sorted(tiers)),
        )

    if state is not None:
        changes = update_state(
            state,
            rows,
            scope="all_drives" if options.all_drives else "my_drive",
        )
        apply_state(rows, state)
        save_state(options.state_path, state)
        for line in describe_changes(changes):
            log.info(line)

    if options.script_ids_out is not None:
        options.script_ids_out.write_text(
            format_script_ids(rows, extra_ids=file_ids), encoding="utf-8"
        )
        log.info("Wrote script IDs file to %s", options.script_ids_out)

    return rows
