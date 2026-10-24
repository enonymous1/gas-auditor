"""projects.getContent parsing: file statistics and the appsscript.json manifest.

In the getContent payload the manifest is the file with name == 'appsscript'
and type == 'JSON', and its `source` is a JSON *string*, not an object.
Advanced services live at dependencies.enabledAdvancedServices -- there is
no top-level 'advancedServices' key.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any

from .retry import execute_with_retry

log = logging.getLogger(__name__)


def parse_manifest(files: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract audit fields from the appsscript.json manifest file, if any."""
    out: dict[str, Any] = {
        "oauth_scopes": [],
        "advanced_services": [],
        "manifest_time_zone": "",
        "runtime_version": "",
        "has_webapp": False,
        "has_execution_api": False,
    }
    manifest_file = next(
        (f for f in files if f.get("name") == "appsscript" and f.get("type") == "JSON"),
        None,
    )
    if manifest_file is None or not manifest_file.get("source"):
        return out

    try:
        manifest = json.loads(manifest_file["source"])
    except (json.JSONDecodeError, TypeError):
        log.warning("Manifest for a project was not valid JSON; skipping it.")
        return out

    out["oauth_scopes"] = list(manifest.get("oauthScopes") or [])
    out["manifest_time_zone"] = manifest.get("timeZone") or ""
    out["runtime_version"] = manifest.get("runtimeVersion") or ""
    out["has_webapp"] = "webapp" in manifest
    out["has_execution_api"] = "executionApi" in manifest

    deps = manifest.get("dependencies") or {}
    for svc in deps.get("enabledAdvancedServices") or []:
        # Shape: {"userSymbol": "Drive", "serviceId": "drive", "version": "v2"}
        label = svc.get("userSymbol") or svc.get("serviceId") or "?"
        out["advanced_services"].append(
            f"{label} (serviceId={svc.get('serviceId', '?')}, {svc.get('version', '?')})"
        )
    return out


def summarise_content(content: dict[str, Any]) -> dict[str, Any]:
    """File statistics + manifest fields from a projects.getContent payload."""
    files = content.get("files", []) or []

    counts = Counter(f.get("type", "UNKNOWN") for f in files)
    functions: list[str] = []
    total_chars = 0
    for f in files:
        total_chars += len(f.get("source") or "")
        # functionSet is only present on SERVER_JS files that define functions.
        for fn in (f.get("functionSet") or {}).get("values", []) or []:
            if fn.get("name"):
                functions.append(fn["name"])

    result: dict[str, Any] = {
        "file_count": len(files),
        "file_counts_by_type": dict(counts),
        "server_js_count": counts.get("SERVER_JS", 0),
        "html_count": counts.get("HTML", 0),
        "json_count": counts.get("JSON", 0),
        "function_count": len(functions),
        "function_names": sorted(set(functions)),
        "total_source_chars": total_chars,
    }
    result.update(parse_manifest(files))
    result["oauth_scope_count"] = len(result["oauth_scopes"])
    return result


def fetch_content(script: Any, script_id: str) -> dict[str, Any]:
    """Call projects.getContent for one project and summarise it."""
    content = execute_with_retry(
        script.projects().getContent(scriptId=script_id)
    )
    return summarise_content(content)
