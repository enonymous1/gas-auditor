"""projects.getMetrics: active users and execution counts.

Payload shape: {"activeUsers": [{startTime, endTime, value}, ...],
                "totalExecutions": [...], "failedExecutions": [...]}
`value` is a *string* containing an integer. Executions are additive across
intervals; active users are unique-per-interval, so summing them would
double-count -- summarise_metrics() reports the most recent interval instead.

metricsGranularity is REQUIRED by the API: 'DAILY' (~last 7 days) or
'WEEKLY'. Calling getMetrics without one returns empty metrics.
"""

from __future__ import annotations

from typing import Any

from .retry import execute_with_retry


def summarise_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Collapse a getMetrics interval payload into flat numbers."""

    def _values(key: str) -> list[dict[str, Any]]:
        return metrics.get(key, []) or []

    def _as_int(entry: dict[str, Any]) -> int:
        try:
            return int(entry.get("value") or 0)
        except (TypeError, ValueError):
            return 0

    active = sorted(_values("activeUsers"), key=lambda e: e.get("endTime", ""))
    return {
        "active_users_latest": _as_int(active[-1]) if active else 0,
        "total_executions": sum(_as_int(e) for e in _values("totalExecutions")),
        "failed_executions": sum(_as_int(e) for e in _values("failedExecutions")),
    }


def fetch_metrics(script: Any, script_id: str, granularity: str) -> dict[str, Any]:
    """Call projects.getMetrics for one project and summarise it."""
    resp = execute_with_retry(
        script.projects().getMetrics(
            scriptId=script_id, metricsGranularity=granularity
        )
    )
    return summarise_metrics(resp)
