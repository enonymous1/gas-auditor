"""Output: CSV export and Polars DataFrame conversion.

In memory, list columns (oauth_scopes, function_names, ...) stay as lists
and breakdowns (file_counts_by_type, process_types, ...) stay as dicts --
the rich form Polars wants. For CSV they are flattened: lists to
'a; b' and dicts to 'K=1; K2=2'.
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path
from typing import Any

from .config import AUDIT_FIELDS

log = logging.getLogger(__name__)


def csv_ready(row: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a row with list/dict values flattened for CSV."""
    flat: dict[str, Any] = {}
    for field in AUDIT_FIELDS:
        value = row.get(field, "")
        if isinstance(value, list):
            flat[field] = "; ".join(str(v) for v in value)
        elif isinstance(value, dict):
            flat[field] = "; ".join(f"{k}={value[k]}" for k in sorted(value, key=str))
        else:
            flat[field] = value
    return flat


def render_csv(rows: list[dict[str, Any]]) -> str:
    """Return the audit rows as CSV text (used by export_csv and by the
    web dashboard's /api/export download)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=AUDIT_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow(csv_ready(row))
    return buf.getvalue()


def export_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.write_text(render_csv(rows), encoding="utf-8")
    log.info("Wrote %d rows to %s", len(rows), output_path)


def to_dataframe(rows: list[dict[str, Any]]):
    """Return the audit rows as a Polars DataFrame (list/dict columns kept
    as native Polars List/Struct values -- richer than the flattened CSV).

        import polars as pl
        df = to_dataframe(rows)
        df.filter(pl.col('failed_executions') > 0)
    """
    try:
        import polars as pl
    except ImportError as exc:
        raise RuntimeError(
            "polars is not installed -- `pip install polars`, or just use the CSV."
        ) from exc
    # Restrict/reorder every row to AUDIT_FIELDS so the schema is stable
    # even if a helper later adds an internal key.
    return pl.DataFrame([{f: row.get(f) for f in AUDIT_FIELDS} for row in rows])
