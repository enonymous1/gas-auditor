"""Command-line entry point: `gas-audit` (or `python -m gas_auditor`)."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .output import export_csv
from .pipeline import ScanOptions, run_scan

log = logging.getLogger("gas_auditor")


def build_parser() -> argparse.ArgumentParser:
    """Define the `gas-audit` flags (see pipeline.ScanOptions for what each
    one controls -- the parser only collects values, it runs nothing)."""
    parser = argparse.ArgumentParser(
        description="Audit / inventory all Google Apps Script projects in Drive."
    )
    parser.add_argument("--credentials", default="credentials.json",
                        help="OAuth client JSON from Cloud Console "
                        "(default: credentials.json)")
    parser.add_argument("--token", default="token.json",
                        help="Cached OAuth token (default: token.json)")
    parser.add_argument("--output", default="gas_audit.csv",
                        help="CSV output path (default: gas_audit.csv)")
    parser.add_argument("--metrics-granularity", choices=["DAILY", "WEEKLY"],
                        default="WEEKLY",
                        help="DAILY = last ~7 days, WEEKLY = weekly buckets "
                        "(default: WEEKLY)")
    parser.add_argument("--process-limit", type=int, default=50,
                        help="Max recent processes sampled per project (default: 50)")
    parser.add_argument("--process-since-days", type=int, default=None,
                        help="Only count processes from the last N days "
                        "(default: no window)")
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
    """Parse flags, run the shared pipeline (pipeline.run_scan), write
    the CSV, and summarise stage errors. Returns 0 always: a stage error
    is data (it lands in the row's *_error column and in the summary
    below), not a failed run."""
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    def _progress(i: int, total: int, drive_file: dict) -> None:
        log.info("[%d/%d] %s", i, total,
                 drive_file.get("name", drive_file["id"]))

    rows = run_scan(
        ScanOptions(
            credentials_path=Path(args.credentials),
            token_path=Path(args.token),
            metrics_granularity=args.metrics_granularity,
            process_limit=args.process_limit,
            process_since_days=args.process_since_days,
            all_drives=args.all_drives,
            github_candidates_path=(
                Path(args.github_candidates) if args.github_candidates else None
            ),
            github_mapping_path=(
                Path(args.github_mapping) if args.github_mapping else None
            ),
            state_path=None if args.no_state else Path(args.state),
            script_ids=list(args.script_id),
            script_ids_file=(
                Path(args.script_ids_file) if args.script_ids_file else None
            ),
            script_ids_out=(
                Path(args.script_ids_out) if args.script_ids_out else None
            ),
            on_project=_progress,
        )
    )

    export_csv(rows, Path(args.output))

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
