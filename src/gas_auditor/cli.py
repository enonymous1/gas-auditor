"""Command-line entry point: `gas-audit` (or `python -m gas_auditor`)."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .audit import audit_project
from .auth import build_services, get_credentials
from .discovery import discover_projects, format_script_ids, read_script_ids
from .github_link import enrich_rows, load_candidates, load_mapping
from .output import export_csv
from .tracking import (
    apply_state,
    describe_changes,
    load_state,
    save_state,
    update_state,
)

log = logging.getLogger("gas_auditor")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit / inventory all Google Apps Script projects in Drive."
    )
    parser.add_argument("--credentials", default="credentials.json",
                        help="OAuth client JSON from Cloud Console (default: credentials.json)")
    parser.add_argument("--token", default="token.json",
                        help="Cached OAuth token (default: token.json)")
    parser.add_argument("--output", default="gas_audit.csv",
                        help="CSV output path (default: gas_audit.csv)")
    parser.add_argument("--metrics-granularity", choices=["DAILY", "WEEKLY"],
                        default="WEEKLY",
                        help="DAILY = last ~7 days, WEEKLY = weekly buckets (default: WEEKLY)")
    parser.add_argument("--process-limit", type=int, default=50,
                        help="Max recent processes sampled per project (default: 50)")
    parser.add_argument("--process-since-days", type=int, default=None,
                        help="Only count processes from the last N days (default: no window)")
    parser.add_argument("--all-drives", action="store_true",
                        help="Also discover projects in shared drives")
    parser.add_argument("--github-candidates", default=None, metavar="PATH",
                        help="GitHub repo candidates for association matching: "
                             "a JSON inventory export (e.g. from ss-github-repos) "
                             "or a directory of local repo checkouts. Offline; "
                             "omit to skip GitHub matching entirely.")
    parser.add_argument("--github-mapping", default=None, metavar="PATH",
                        help="Curated {scriptId: 'owner/repo'} JSON overrides "
                             "(confirmed tier) for GitHub matching.")
    parser.add_argument("--script-id", action="append", default=[], metavar="ID",
                        help="Also audit this scriptId directly (repeatable). "
                             "The way to include container-bound projects, "
                             "which Drive listing hides -- get the ID from "
                             "the project's script-editor URL.")
    parser.add_argument("--script-ids-file", default=None, metavar="PATH",
                        help="Text file of scriptIds, one per line (# comments "
                             "allowed), to audit directly (same purpose as "
                             "--script-id).")
    parser.add_argument("--script-ids-out", default=None, metavar="PATH",
                        help="After the run, (over)write this file with every "
                             "known project ID (annotated, editable) -- the "
                             "easy starting point for adding missing "
                             "container-bound IDs before the next run.")
    parser.add_argument("--state", default="gas_audit_state.json", metavar="PATH",
                        help="Cross-run tracking state file: first/last seen "
                             "per project + missing detection "
                             "(default: gas_audit_state.json)")
    parser.add_argument("--no-state", action="store_true",
                        help="Disable cross-run tracking for this run")
    parser.add_argument("--verbose", action="store_true", help="DEBUG logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    creds = get_credentials(Path(args.credentials), Path(args.token))
    drive, script = build_services(creds)

    # Tracking state is loaded BEFORE discovery: its known project IDs
    # double as discovery seeds, so container-bound projects (invisible
    # to Drive listing) stay in the audit once they've ever been seeded.
    state = None if args.no_state else load_state(Path(args.state))

    file_ids = (
        read_script_ids(Path(args.script_ids_file)) if args.script_ids_file else []
    )
    seed_ids: list[str] = list(args.script_id) + file_ids
    if state is not None:
        seed_ids.extend(state.get("projects", {}).keys())

    log.info("Discovering Apps Script projects in Drive...")
    drive_files = discover_projects(
        drive, all_drives=args.all_drives, extra_ids=seed_ids
    )
    log.info("Found %d project(s). Auditing...", len(drive_files))

    rows = []
    for i, drive_file in enumerate(drive_files, start=1):
        log.info("[%d/%d] %s", i, len(drive_files),
                 drive_file.get("name", drive_file["id"]))
        rows.append(
            audit_project(
                drive_file,
                script,
                metrics_granularity=args.metrics_granularity,
                process_limit=args.process_limit,
                process_since_days=args.process_since_days,
            )
        )

    if args.github_candidates or args.github_mapping:
        candidates = (
            load_candidates(Path(args.github_candidates))
            if args.github_candidates else []
        )
        mapping = load_mapping(Path(args.github_mapping)) if args.github_mapping else {}
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
            state, rows,
            scope="all_drives" if args.all_drives else "my_drive",
        )
        apply_state(rows, state)
        save_state(Path(args.state), state)
        for line in describe_changes(changes):
            log.info(line)

    export_csv(rows, Path(args.output))

    if args.script_ids_out:
        out_path = Path(args.script_ids_out)
        out_path.write_text(
            format_script_ids(rows, extra_ids=file_ids), encoding="utf-8"
        )
        log.info("Wrote script IDs file to %s", out_path)

    errored = sum(
        1 for r in rows
        if r["project_error"] or r["content_error"]
        or r["metrics_error"] or r["processes_error"]
    )
    log.info(
        "Done: %d projects, %d with at least one stage error (see *_error columns).",
        len(rows), errored,
    )
    return 0
