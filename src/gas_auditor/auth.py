"""OAuth 2.0 (Desktop-app / installed-app flow) and API client construction.

Token is cached in token.json. Delete token.json if SCOPES ever change --
get_credentials() also detects a cached token missing a required scope and
forces a fresh consent instead of failing later with a confusing 403.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .config import SCOPES

log = logging.getLogger(__name__)


def get_credentials(credentials_path: Path, token_path: Path) -> Credentials:
    """Load cached OAuth credentials, refreshing them or running the local
    browser consent flow when needed."""
    creds: Credentials | None = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        granted = set(creds.scopes or [])
        if granted and not set(SCOPES).issubset(granted):
            log.warning("Cached token is missing scopes; re-running consent flow.")
            creds = None

    if creds is not None and not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = None

    if creds is None:
        if not credentials_path.exists():
            raise FileNotFoundError(
                f"{credentials_path} not found. Download an OAuth client "
                "(type: Desktop app) JSON from Google Cloud Console -> "
                "APIs & Services -> Credentials, and save it there. "
                "See README.md."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
        # port=0 lets the OS pick a free port for the local redirect server.
        creds = flow.run_local_server(port=0)

    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def build_services(creds: Credentials) -> tuple[Any, Any]:
    """Return (drive_service, script_service). cache_discovery=False avoids
    stale discovery-doc pickles when Google revs an API."""
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    script = build("script", "v1", credentials=creds, cache_discovery=False)
    return drive, script
