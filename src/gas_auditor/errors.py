"""Error formatting shared by every audit stage."""

from __future__ import annotations

from googleapiclient.errors import HttpError


def err_str(exc: Exception) -> str:
    """Compact, CSV-safe one-line error string."""
    if isinstance(exc, HttpError):
        status = exc.resp.status if exc.resp is not None else "?"
        return f"HttpError {status}: {exc.reason or exc}"
    return f"{type(exc).__name__}: {exc}"
