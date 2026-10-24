"""Curated OAuth scope registry for the dashboard.

For each well-known Google scope: a plain-language definition, Google's
sensitivity classification where it's established (Non-sensitive /
Sensitive / Restricted, per Google's OAuth verification docs), and a link
to the scope's section in Google's official scope reference
(https://developers.google.com/identity/protocols/oauth2/scopes).

Unknown scopes still get a view: the raw URL, a generic note, and the
reference index link -- the dashboard never invents a definition.
"""

from __future__ import annotations

from typing import Any

_PREFIX = "https://www.googleapis.com/auth/"
_INDEX = "https://developers.google.com/identity/protocols/oauth2/scopes"

# tail-after-auth/ -> docs page anchor on the reference index
_ANCHORS = {
    "drive": "drive", "spreadsheets": "sheets", "script": "script",
    "gmail": "gmail", "calendar": "calendar", "documents": "docs",
    "presentations": "slides", "forms": "forms", "userinfo": "oauth2",
    "openid": "oauth2", "directory": "admin", "tasks": "tasks",
    "youtube": "youtube", "contacts": "people", "people": "people",
}


def _docs_url(tail: str) -> str:
    head = tail.split(".")[0].split("/")[0]
    anchor = _ANCHORS.get(head)
    return f"{_INDEX}#{anchor}" if anchor else _INDEX


# tail-after-auth/ -> (definition, sensitivity)
_KNOWN: dict[str, tuple[str, str]] = {
    # -- This auditor's own scopes --
    "drive.metadata.readonly": (
        "See metadata (names, types, timestamps) of files in Google Drive. "
        "No file contents.", "Restricted"),
    "script.projects.readonly": (
        "Read Google Apps Script projects (metadata and content).", "Sensitive"),
    "script.metrics": (
        "Read Apps Script usage metrics (executions, active users).", "Sensitive"),
    "script.processes": (
        "Read Apps Script process/execution history.", "Sensitive"),
    # -- Drive --
    "drive.readonly": (
        "See and download all files in Google Drive, including contents.",
        "Restricted"),
    "drive": (
        "See, edit, create, and delete all files in Google Drive.",
        "Restricted"),
    "drive.file": (
        "Access only the Drive files this app creates or the user opens "
        "with it.", "Sensitive"),
    "drive.appdata": (
        "Access the app's own hidden configuration folder in Drive.",
        "Sensitive"),
    # -- Apps Script runtime / API --
    "script.projects": (
        "Create, read, and update Apps Script projects.", "Sensitive"),
    "script.deployments": (
        "Manage Apps Script deployments (web apps, add-ons, API executables).",
        "Sensitive"),
    "script.deployments.readonly": (
        "Read Apps Script deployments.", "Sensitive"),
    "script.external_request": (
        "Make outbound HTTP requests from an Apps Script (UrlFetch).",
        "Sensitive"),
    "script.scriptapp": (
        "Manage an Apps Script's triggers and deployments on the user's "
        "behalf.", "Sensitive"),
    "script.send_mail": (
        "Send email as the user from an Apps Script (MailApp).", "Sensitive"),
    "script.storage": (
        "Access an Apps Script's stored data.", "Sensitive"),
    # -- Workspace apps commonly requested by scripts --
    "spreadsheets.readonly": (
        "Read Google Sheets spreadsheets.", "Sensitive"),
    "spreadsheets": (
        "Read and write Google Sheets spreadsheets.", "Sensitive"),
    "documents.readonly": (
        "Read Google Docs documents.", "Sensitive"),
    "documents": (
        "Read and write Google Docs documents.", "Sensitive"),
    "presentations.readonly": (
        "Read Google Slides presentations.", "Sensitive"),
    "presentations": (
        "Read and write Google Slides presentations.", "Sensitive"),
    "forms.body.readonly": (
        "Read Google Forms structure.", "Sensitive"),
    "forms.body": (
        "Read and write Google Forms structure.", "Sensitive"),
    "forms.responses.readonly": (
        "Read responses submitted to Google Forms.", "Sensitive"),
    "gmail.readonly": (
        "Read Gmail messages and settings.", "Restricted"),
    "gmail.modify": (
        "Read and modify Gmail messages (labels, archive, trash) but not "
        "delete permanently.", "Restricted"),
    "gmail.send": (
        "Send email from the user's Gmail account.", "Sensitive"),
    "gmail.compose": (
        "Create, edit, and send Gmail drafts and messages.", "Sensitive"),
    "calendar.readonly": (
        "Read calendars and events.", "Sensitive"),
    "calendar": (
        "Read and write calendars and events.", "Sensitive"),
    "calendar.events": (
        "Read and write calendar events.", "Sensitive"),
    "tasks.readonly": (
        "Read Google Tasks lists and tasks.", "Sensitive"),
    "tasks": (
        "Read and write Google Tasks lists and tasks.", "Sensitive"),
    "youtube.readonly": (
        "Read the user's YouTube account data.", "Sensitive"),
    # -- Identity --
    "userinfo.email": (
        "See the user's email address.", "Non-sensitive"),
    "userinfo.profile": (
        "See the user's basic profile (name, photo).", "Non-sensitive"),
    "openid": (
        "Associate the user with their personal info on Google "
        "(OpenID Connect sign-in).", "Non-sensitive"),
}


def scope_view(scope_url: str) -> dict[str, Any]:
    """Display dict for one scope URL: {url, short, definition,
    sensitivity, docs_url, known}. `short` strips the constant auth/
    prefix, matching how the table has always shown scopes."""
    url = scope_url or ""
    tail = url.removeprefix(_PREFIX)
    short = tail if url.startswith(_PREFIX) else url
    known = _KNOWN.get(tail)
    if known:
        definition, sensitivity = known
    else:
        definition = (
            "No curated summary for this scope yet -- Google's reference "
            "(linked below) is the authoritative definition."
        )
        sensitivity = ""
    return {
        "url": url,
        "short": short,
        "definition": definition,
        "sensitivity": sensitivity,
        "docs_url": _docs_url(tail),
        "known": bool(known),
    }
