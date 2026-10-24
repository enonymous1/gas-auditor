"""Shared fake audit row for the web tests."""

FAKE_ROW = {
    "project_name": "My Script",
    "script_id": "ABC",
    "web_view_link": "https://example.invalid/abc",
    "drive_modified_time": "2026-10-20T17:20:00Z",
    "file_count": 3,
    "oauth_scopes": ["https://www.googleapis.com/auth/spreadsheets.readonly"],
    "last_execution_status": "COMPLETED",
    "last_execution_time": "2026-10-20T01:00:00Z",
    "failed_process_count": 0,
    "processes_error": "",
    "project_error": "",
    "content_error": "",
    "metrics_error": "",
}
