"""Retry wrapper for Google API requests: 429 / 5xx with backoff.

Why this exists: the Apps Script API enforces *per-minute per-user*
quotas ('GetMetrics requests per minute per user', etc.), and an audit
fires 4 calls per project as fast as the client can go. A first live run
(13 projects) hit 429s on 4 projects purely from burst rate. Sleeping
with exponential backoff until the minute window rolls over is the
correct behaviour for a batch audit -- the alternative (recording the
429 as a stage error) loses data for no benefit.

Retry-After (when Google sends it) wins over the computed backoff.
Non-retryable errors (403 permission, 404, ...) raise immediately.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable

from .config import API_MAX_RETRIES, API_RETRY_BASE_SECONDS

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_DELAY = 60.0


def _status_of(exc: BaseException) -> int | None:
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _retry_after_of(exc: BaseException) -> float | None:
    resp = getattr(exc, "resp", None)
    get = getattr(resp, "get", None)
    if callable(get):
        value = get("retry-after") or get("Retry-After")
        try:
            return float(value) if value else None
        except (TypeError, ValueError):
            return None
    return None


def execute_with_retry(
    request: Any,
    *,
    max_retries: int = API_MAX_RETRIES,
    base_delay: float = API_RETRY_BASE_SECONDS,
    sleeper: Callable[[float], None] = time.sleep,
) -> Any:
    """Execute a googleapiclient request, retrying retryable HTTP errors
    with exponential backoff + jitter. `sleeper` is injectable for tests.
    Returns the response payload; re-raises the last error when retries
    are exhausted, and any non-retryable error immediately."""
    attempt = 0
    while True:
        try:
            return request.execute()
        except Exception as exc:  # noqa: BLE001 -- narrowed by status below
            status = _status_of(exc)
            if status not in RETRYABLE_STATUS or attempt >= max_retries:
                raise
            backoff = min(base_delay * (2 ** attempt), _MAX_DELAY)
            delay = max(backoff, _retry_after_of(exc) or 0.0)
            delay += random.uniform(0, 1)
            log.info(
                "HTTP %s (attempt %d/%d) -- retrying in %.1fs",
                status, attempt + 1, max_retries + 1, delay,
            )
            sleeper(delay)
            attempt += 1
