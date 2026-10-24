"""Static configuration: OAuth scopes, Drive query constants, output schema.

No logic lives here -- this module is the single place to change what the
auditor asks Google for, or what columns the audit produces.
"""

from __future__ import annotations

# Least-privilege, read-only scopes -- enough for every call in this package:
#   drive.metadata.readonly : Drive files.list metadata (no file contents)
#   script.projects.readonly: projects.get / projects.getContent
#   script.metrics          : projects.getMetrics
#   script.processes        : processes.listScriptProcesses
SCOPES = [
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/script.projects.readonly",
    "https://www.googleapis.com/auth/script.metrics",
    "https://www.googleapis.com/auth/script.processes",
]

SCRIPT_MIMETYPE = "application/vnd.google-apps.script"

# API resilience: the Apps Script API enforces per-minute per-user quotas,
# and an audit bursts 4 calls/project. Retry 429/5xx with exponential
# backoff (see retry.py). 5 retries at base 2s spans ~60s worst case --
# enough for a minute quota window to roll over.
API_MAX_RETRIES = 5
API_RETRY_BASE_SECONDS = 2.0

# Flat output columns, in order. Every audit row has exactly these keys,
# which is what makes both csv.DictWriter and pl.DataFrame(rows) happy.
AUDIT_FIELDS = [
    "project_name",
    "script_id",
    "drive_modified_time",
    "drive_created_time",
    "web_view_link",
    "parent_id",  # set => container-bound script
    "creator_email",
    "last_modify_user_email",
    "project_create_time",
    "project_update_time",
    # --- content / manifest ---
    "file_count",
    "file_counts_by_type",  # dict in memory, "HTML=1; JSON=1; ..." in CSV
    "server_js_count",
    "html_count",
    "json_count",
    "function_count",
    "function_names",  # list in memory, "; "-joined in CSV
    "total_source_chars",
    "oauth_scopes",  # list in memory, "; "-joined in CSV
    "oauth_scope_count",
    "advanced_services",  # e.g. "Drive (serviceId=drive, v2)"
    "manifest_time_zone",
    "runtime_version",
    "has_webapp",
    "has_execution_api",
    # --- metrics (window depends on granularity) ---
    "metrics_granularity",
    "active_users_latest",  # latest interval only: unique users are NOT additive
    "total_executions",  # summed over returned intervals (additive)
    "failed_executions",  # summed over returned intervals (additive)
    # --- recent processes / executions ---
    "recent_process_count",
    "process_types",  # dict in memory, "TIME_DRIVEN=12; ..." in CSV
    "process_statuses",  # dict in memory, "COMPLETED=40; ..." in CSV
    "failed_process_count",  # FAILED + TIMED_OUT within the sampled processes
    "last_execution_time",
    "last_execution_type",
    "last_execution_status",
    "last_execution_function",
    # --- Cross-run tracking (filled when state tracking is enabled) ---
    "first_seen",               # first run (UTC) that saw this project
    "last_seen",                # most recent run (UTC) that saw it
    # --- GitHub association (spike; filled only when enrichment runs) ---
    "github_repo",              # 'owner/repo' of best candidate, '' if none
    "github_repo_url",
    "github_match",             # confirmed|probable|possible|none; '' = not checked
    "github_evidence",          # signals behind the tier, '; '-joined
    # --- per-stage errors (empty string = that stage succeeded) ---
    "project_error",
    "content_error",
    "metrics_error",
    "processes_error",
]
