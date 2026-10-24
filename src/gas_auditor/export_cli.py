"""gas-audit-export: download project source code to local folders.

Selectors (unioned, de-duplicated):
  --script-id ID ...        explicit projects (the bound-project route)
  --script-ids-file PATH    an IDs file (same format as gas-audit's)
  --from-csv PATH           the script_id column of a gas_audit.csv
  --from-state PATH         every project ID in a tracking state file
  (none of the above)       Drive discovery, seeded from the default
                            state file when one exists -- i.e. "all of
                            them, bound included, as far as we know"
  --discover                add Drive discovery on top of the selectors
"""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

from .auth import build_services, get_credentials
from .discovery import discover_projects, read_script_ids
from .exporter import export_projects
from .tracking import load_state

log = logging.getLogger(__name__)


def _ids_from_csv(path: Path) -> list[str]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return [
            row["script_id"].strip()
            for row in csv.DictReader(fh)
            if row.get("script_id")
        ]


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(message)s"
    )
    parser = argparse.ArgumentParser(
        prog="gas-audit-export",
        description="Download Apps Script project source code locally.",
    )
    parser.add_argument("--output-dir", default="gapps-projects", metavar="DIR",
                        help="Export root (default: gapps-projects).")
    parser.add_argument("--credentials", default="credentials.json")
    parser.add_argument("--token", default="token.json")
    parser.add_argument("--script-id", action="append", default=[], metavar="ID",
                        help="Export this scriptId (repeatable).")
    parser.add_argument("--script-ids-file", default=None, metavar="PATH",
                        help="IDs file, one per line (# comments allowed).")
    parser.add_argument("--from-csv", default=None, metavar="PATH",
                        help="Take script IDs from a gas_audit.csv export.")
    parser.add_argument("--from-state", default=None, metavar="PATH",
                        help="Take script IDs from a tracking state file.")
    parser.add_argument("--state", default="gas_audit_state.json", metavar="PATH",
                        help="Default state file used to seed discovery "
                             "(when it exists).")
    parser.add_argument("--discover", action="store_true",
                        help="Also run Drive discovery (seeded from --state).")
    parser.add_argument("--all-drives", action="store_true",
                        help="Discovery includes shared drives.")
    args = parser.parse_args(argv)

    ids: list[str] = list(args.script_id)
    if args.script_ids_file:
        ids += read_script_ids(Path(args.script_ids_file))
    if args.from_csv:
        ids += _ids_from_csv(Path(args.from_csv))
    if args.from_state:
        ids += list(load_state(Path(args.from_state)).get("projects", {}).keys())

    explicit = bool(ids)
    creds = get_credentials(Path(args.credentials), Path(args.token))
    drive, script = build_services(creds)

    if args.discover or not explicit:
        state_ids: list[str] = []
        state_path = Path(args.state)
        if state_path.exists():
            state_ids = list(
                load_state(state_path).get("projects", {}).keys()
            )
        log.info("Discovering projects in Drive (seeded with %d state IDs)...",
                 len(state_ids))
        found = discover_projects(
            drive, all_drives=args.all_drives, extra_ids=state_ids
        )
        ids += [f["id"] for f in found]

    ids = list(dict.fromkeys(i for i in ids if i))
    if not ids:
        log.error("No project IDs selected -- nothing to export.")
        return 2

    root = Path(args.output_dir)
    log.info("Exporting %d project(s) to %s ...", len(ids), root)
    results = export_projects(script, ids, root)
    failed = 0
    for r in results:
        if r.ok:
            stale = f" ({len(r.stale_files)} stale file(s) kept)" if r.stale_files else ""
            log.info("✓ %s -> %s [%d file(s)]%s",
                     r.title or r.script_id, r.directory,
                     len(r.files_written), stale)
        else:
            failed += 1
            log.error("✗ %s: %s", r.script_id, r.error)
    log.info("Done: %d exported, %d failed.", len(results) - failed, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
