"""GitHub README resolution + rendering for the project detail view.

Source order (offline first, consistent with the matcher's spike design):
  1. The matched candidate's local checkout (readme_path from the
     github_link scanner, or a README file in its local_path root).
  2. raw.githubusercontent.com for the repo's default branch (the
     candidate's, when known), falling back to main, then master.
     Public repos only -- there is no token support yet, by design.

Rendering uses the `markdown` package (part of the .[web] extra) with a
light sanitiser: rendered READMEs come from the user's own repos, but
script/iframe tags, inline event handlers, and javascript: URLs are
stripped before the HTML is marked safe for the template. Without the
markdown package the text is shown escaped in a <pre>.

The HTTP getter is injectable so tests never touch the network.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any, Callable

_RAW = "https://raw.githubusercontent.com/{repo}/{branch}/README.md"
_README_NAMES = ("README.md", "readme.md", "README.markdown", "README")


def _default_http_get(url: str):
    import httpx

    # trust_env=False: deterministic behaviour, no proxy-env surprises.
    return httpx.get(url, timeout=10.0, follow_redirects=True, trust_env=False)


def _sanitise(rendered: str) -> str:
    rendered = re.sub(r"<(script|iframe|object|embed)\b.*?</\1>", "",
                      rendered, flags=re.I | re.S)
    rendered = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*')", "", rendered, flags=re.I)
    rendered = re.sub(r"href\s*=\s*([\"'])\s*javascript:[^\"']*\1",
                      'href="#"', rendered, flags=re.I)
    return rendered


def render_markdown(text: str) -> str:
    """Markdown -> sanitised HTML (or an escaped <pre> fallback)."""
    try:
        import markdown
    except ImportError:
        return f"<pre>{html.escape(text)}</pre>"
    return _sanitise(
        markdown.markdown(text, extensions=["fenced_code", "tables"])
    )


def _local_readme_text(candidate: dict[str, Any] | None) -> tuple[str, str] | None:
    """(text, source label) from the candidate's local checkout, if any."""
    if not candidate:
        return None
    path = candidate.get("readme_path") or ""
    if path and Path(path).is_file():
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace"), \
                f"local checkout: {path}"
        except OSError:
            pass
    local = candidate.get("local_path") or ""
    if local:
        for name in _README_NAMES:
            p = Path(local) / name
            if p.is_file():
                try:
                    return p.read_text(encoding="utf-8", errors="replace"), \
                        f"local checkout: {p}"
                except OSError:
                    pass
    return None


def resolve_readme(
    row: dict[str, Any],
    candidate: dict[str, Any] | None,
    *,
    http_get: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Return {state: 'ok'|'none', html, source, message} for a row's
    linked GitHub repo. Never raises -- failures are display states."""
    repo = row.get("github_repo") or ""
    if not repo:
        return {"state": "none", "html": "", "source": "",
                "message": "No GitHub association for this project "
                           "(matching off, or no candidate matched)."}

    local = _local_readme_text(candidate)
    if local:
        text, source = local
        return {"state": "ok", "html": render_markdown(text),
                "source": source, "message": ""}

    if "/" in repo:
        get = http_get or _default_http_get
        branches: list[str] = []
        if candidate and candidate.get("default_branch"):
            branches.append(candidate["default_branch"])
        for b in ("main", "master"):
            if b not in branches:
                branches.append(b)
        for branch in branches:
            try:
                resp = get(_RAW.format(repo=repo, branch=branch))
            except Exception:  # noqa: BLE001 -- network is best-effort here
                break
            if getattr(resp, "status_code", 0) == 200 and resp.text.strip():
                return {"state": "ok", "html": render_markdown(resp.text),
                        "source": f"raw.githubusercontent.com ({branch})",
                        "message": ""}
    return {"state": "none", "html": "", "source": "",
            "message": "No README found in a local checkout or on GitHub "
                       "(remote fetch covers public repos only)."}


def candidate_for_row(
    row: dict[str, Any], candidates: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """The candidate whose full_name matches the row's linked repo."""
    repo = row.get("github_repo") or ""
    if not repo:
        return None
    for c in candidates:
        if c.get("full_name") == repo:
            return c
    return None
