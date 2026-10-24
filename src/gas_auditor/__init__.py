"""gas_auditor -- auditor / inventory tool for Google Apps Script projects.

Public API (everything the CLI and library users need):

    from gas_auditor import (
        get_credentials, build_services,   # auth
        discover_projects,                 # Drive discovery
        audit_project,                     # one-row orchestration
        export_csv, to_dataframe,          # output
        AUDIT_FIELDS, SCOPES,              # config
    )

Module map (separation of concerns):
    config.py     scopes, Drive constants, output schema -- no logic
    auth.py       OAuth flow + API client construction
    discovery.py  Drive API v3 project discovery
    project.py    Apps Script projects.get
    content.py    projects.getContent: file stats + appsscript.json manifest
    metrics.py    projects.getMetrics
    processes.py  processes.listScriptProcesses (recent executions)
    audit.py      per-project orchestration with per-stage error isolation
    output.py     CSV export + Polars DataFrame
    github_link.py offline GitHub-association matcher (evidence tiers, spike)
    tracking.py   cross-run state: first/last seen + missing detection
    retry.py      429/5xx exponential-backoff wrapper for API calls
    cli.py        argparse entry point (`gas-audit` / `python -m gas_auditor`)
    errors.py     shared one-line error formatting
    web/          optional Flask/Jinja dashboard subpackage (`gas-audit-web`);
                  not imported here, so the core works without Flask
"""

from __future__ import annotations

from .audit import audit_project
from .auth import build_services, get_credentials
from .config import AUDIT_FIELDS, SCOPES, SCRIPT_MIMETYPE
from .content import parse_manifest, summarise_content
from .discovery import discover_projects, fetch_file_meta
from .exporter import ExportResult, export_project, export_projects
from .github_link import enrich_rows, load_candidates, load_mapping, match_project
from .metrics import summarise_metrics
from .output import export_csv, to_dataframe
from .processes import summarise_processes
from .retry import execute_with_retry

__version__ = "0.11.0"

__all__ = [
    "AUDIT_FIELDS",
    "SCOPES",
    "SCRIPT_MIMETYPE",
    "audit_project",
    "build_services",
    "ExportResult",
    "discover_projects",
    "enrich_rows",
    "execute_with_retry",
    "export_csv",
    "export_project",
    "export_projects",
    "fetch_file_meta",
    "get_credentials",
    "load_candidates",
    "load_mapping",
    "match_project",
    "parse_manifest",
    "summarise_content",
    "summarise_metrics",
    "summarise_processes",
    "to_dataframe",
]
