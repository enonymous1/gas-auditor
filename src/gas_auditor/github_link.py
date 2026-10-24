"""GitHub-association detection for Apps Script projects (SPIKE, opt-in).

There is no registry linking a GAS project to a GitHub repo, so this is
evidence-tiered matching, never a boolean lookup. Each project gets:

    github_repo     'owner/repo' of the best candidate ('' if none)
    github_repo_url its URL when known
    github_match    'confirmed' | 'probable' | 'possible' | 'none'
                    ('' when enrichment never ran -- 'none' means
                    "searched, no evidence", '' means "not checked")
    github_evidence human-readable signals, e.g.
                    "name match; contains appsscript.json; 5/7 functions overlap"

Confirmed signals (any one is enough):
  * a curated mapping entry for the scriptId (user-asserted, wins ties)
  * the scriptId appearing in a repo's .clasp.json (clasp workflow)
  * the repo's URL/name appearing in text the project itself carries
    (Drive description, source header comments -- passed in as
    project['explicit_text'] by the caller)

Probable: exact (normalized, non-generic) name match PLUS corroboration
(appsscript.json in repo, or >=2 shared function names, or >=50% function
overlap); or strong function fingerprint (>=3 shared, >=60% overlap)
plus appsscript.json or a fuzzy name match.

Possible: exact name match alone, fuzzy name + appsscript.json, or >=2
shared function names alone.

Candidate sources are offline by design (this is the precision spike --
no live GitHub API yet):
  * load_candidates_json()  -- an inventory export (e.g. ss-github-repos)
  * scan_local_repos()      -- a directory of local repo checkouts
  * load_mapping()          -- curated {scriptId: repo} JSON overrides
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

# Titles too generic to ever count as a name signal on their own.
GENERIC_TITLES = {
    "test", "tests", "untitled", "untitledproject", "code", "main",
    "script", "scripts", "myproject", "project", "appsscript",
    "googleappsscript", "gas", "newproject",
}

# Function names nearly every GAS project shares; not a fingerprint.
COMMON_FUNCTIONS = {
    "onopen", "onedit", "oninstall", "onselectionchange", "doget", "dopost",
    "main", "run", "setup", "init", "test", "myfunction", "createspreadsheet",
}

TIER_RANK = {"none": 0, "possible": 1, "probable": 2, "confirmed": 3}


# ---------------------------------------------------------------------------
# Candidate normalisation / loaders
# ---------------------------------------------------------------------------

def _blank_candidate() -> dict[str, Any]:
    return {
        "name": "", "full_name": "", "html_url": "", "description": "",
        "clasp_script_ids": [], "has_appsscript_json": False,
        "file_names": [], "function_names": [],
        # Provenance for consumers like the dashboard README viewer:
        "local_path": "",      # checkout dir when scanned from disk
        "readme_path": "",     # README file found in that checkout
        "default_branch": "",  # when an inventory export knows it
    }


def _normalise_candidate(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept the several key spellings an inventory export may use."""
    c = _blank_candidate()
    full = (
        raw.get("full_name") or raw.get("fullName") or raw.get("name_with_owner")
        or raw.get("repo") or ""
    )
    name = raw.get("name") or (full.split("/")[-1] if full else "")
    c["name"] = str(name)
    c["full_name"] = str(full) or (str(name) if name else "")
    c["html_url"] = str(raw.get("html_url") or raw.get("url") or raw.get("web_url") or "")
    if not c["html_url"] and c["full_name"] and "/" in c["full_name"]:
        c["html_url"] = "https://github.com/" + c["full_name"]
    c["description"] = str(raw.get("description") or "")

    ids = raw.get("clasp_script_ids") or raw.get("clasp_script_id") or []
    if isinstance(ids, str):
        ids = [ids]
    c["clasp_script_ids"] = [str(i) for i in ids]

    c["has_appsscript_json"] = bool(
        raw.get("has_appsscript_json", raw.get("has_appsscript", False))
    )
    files = raw.get("file_names") or raw.get("files") or []
    c["file_names"] = [str(f) for f in files]
    if any(Path(f).name == "appsscript.json" for f in c["file_names"]):
        c["has_appsscript_json"] = True
    funcs = raw.get("function_names") or raw.get("functions") or []
    c["function_names"] = [str(f) for f in funcs]
    c["local_path"] = str(raw.get("local_path") or "")
    c["readme_path"] = str(raw.get("readme_path") or "")
    c["default_branch"] = str(raw.get("default_branch") or "")
    return c


def load_candidates_json(path: Path) -> list[dict[str, Any]]:
    """Load repo candidates from a JSON inventory export: either a list of
    repo objects, or an object with a 'repos' list. Key spellings are
    flexible -- see _normalise_candidate(). An ss-github-repos snapshot is
    the intended input."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("repos") or data.get("repositories") or []
    return [_normalise_candidate(r) for r in data if isinstance(r, dict)]


def load_mapping(path: Path) -> dict[str, dict[str, str]]:
    """Load curated overrides: {scriptId: 'owner/repo'} or
    {scriptId: {'repo': 'owner/repo', 'url': 'https://...'}}."""
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, str]] = {}
    for script_id, value in (data or {}).items():
        if isinstance(value, str):
            out[str(script_id)] = {"repo": value, "url": ""}
        elif isinstance(value, dict):
            out[str(script_id)] = {
                "repo": str(value.get("repo") or value.get("full_name") or ""),
                "url": str(value.get("url") or value.get("html_url") or ""),
            }
    return out


# ---------------------------------------------------------------------------
# Local checkout scanner
# ---------------------------------------------------------------------------

_FUNC_RE = re.compile(r"function\s+([A-Za-z_$][\w$]*)\s*\(")
_SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "dist", "build"}
_CODE_EXTS = {".gs", ".js", ".ts"}


def _git_remote_url(repo_dir: Path) -> str:
    """Best-effort origin URL from .git/config, normalised to https form."""
    config = repo_dir / ".git" / "config"
    if not config.exists():
        return ""
    text = config.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"\[remote \"origin\"\][^\[]*?url\s*=\s*(\S+)", text, re.S)
    if not m:
        return ""
    url = m.group(1).strip()
    ssh = re.match(r"git@github\.com:(.+?)(?:\.git)?$", url)
    if ssh:
        return "https://github.com/" + ssh.group(1)
    return url.removesuffix(".git")


def _scan_one_repo(repo_dir: Path) -> dict[str, Any]:
    c = _blank_candidate()
    c["name"] = repo_dir.name
    c["local_path"] = str(repo_dir)
    url = _git_remote_url(repo_dir)
    c["html_url"] = url
    m = re.match(r"https://github\.com/([^/]+/[^/]+)$", url)
    c["full_name"] = m.group(1) if m else repo_dir.name

    functions: set[str] = set()
    readme_candidates: list[Path] = []
    for path in repo_dir.rglob("*"):
        if any(part in _SKIP_DIRS for part in path.parts) or not path.is_file():
            continue
        c["file_names"].append(path.name)
        if path.name.lower() in ("readme.md", "readme.markdown", "readme"):
            readme_candidates.append(path)
        if path.name == ".clasp.json":
            try:
                clasp = json.loads(path.read_text(encoding="utf-8"))
                if clasp.get("scriptId"):
                    c["clasp_script_ids"].append(str(clasp["scriptId"]))
            except (json.JSONDecodeError, OSError):
                pass
        elif path.name == "appsscript.json":
            c["has_appsscript_json"] = True
        elif path.suffix in _CODE_EXTS and path.stat().st_size < 2_000_000:
            try:
                functions.update(
                    _FUNC_RE.findall(path.read_text(encoding="utf-8", errors="replace"))
                )
            except OSError:
                pass
    c["function_names"] = sorted(functions)
    if readme_candidates:
        # Shallowest README wins (the repo root's, in the normal layout).
        readme_candidates.sort(key=lambda p: (len(p.parts), p.name.lower()))
        c["readme_path"] = str(readme_candidates[0])
    return c


def scan_local_repos(root: Path) -> list[dict[str, Any]]:
    """Scan a directory of local checkouts. If `root` itself looks like a
    repo (has .git or .clasp.json) it is the single candidate; otherwise
    each immediate subdirectory is treated as one repo."""
    root = Path(root)
    if (root / ".git").exists() or (root / ".clasp.json").exists():
        return [_scan_one_repo(root)]
    return [
        _scan_one_repo(child)
        for child in sorted(root.iterdir())
        if child.is_dir() and not child.name.startswith(".")
    ]


def load_candidates(path: Path) -> list[dict[str, Any]]:
    """Dispatch on the source: a .json file -> inventory export; a
    directory -> local checkout scan."""
    path = Path(path)
    if path.is_dir():
        return scan_local_repos(path)
    return load_candidates_json(path)


# ---------------------------------------------------------------------------
# Matcher
# ---------------------------------------------------------------------------

def normalize_name(name: str) -> str:
    """Lowercase alphanumerics only: 'My-App_Script' -> 'myappscript'."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _name_signals(project_name: str, repo_name: str) -> tuple[bool, bool]:
    """(exact, fuzzy) name match, with generic titles never counting."""
    pn, rn = normalize_name(project_name), normalize_name(repo_name)
    if not pn or not rn or pn in GENERIC_TITLES or rn in GENERIC_TITLES:
        return False, False
    if pn == rn:
        return True, False
    ratio = SequenceMatcher(None, pn, rn).ratio()
    return False, ratio >= 0.85


def _function_overlap(project: dict[str, Any], candidate: dict[str, Any]) -> tuple[int, float]:
    """(shared count, overlap ratio) over non-generic function names."""
    pf = {f.lower() for f in project.get("function_names") or []} - COMMON_FUNCTIONS
    rf = {f.lower() for f in candidate.get("function_names") or []} - COMMON_FUNCTIONS
    if not pf or not rf:
        return 0, 0.0
    shared = len(pf & rf)
    return shared, shared / min(len(pf), len(rf))


def _explicit_hit(project: dict[str, Any], candidate: dict[str, Any]) -> bool:
    """Repo URL or full_name mentioned in text the project itself carries
    (Drive description / source headers, supplied as project['explicit_text'])."""
    text = (project.get("explicit_text") or "").lower()
    if not text:
        return False
    return bool(
        (candidate["html_url"] and candidate["html_url"].lower() in text)
        or (candidate["full_name"] and candidate["full_name"].lower() in text)
    )


def match_project(
    project: dict[str, Any],
    candidates: list[dict[str, Any]],
    mapping: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Return {github_repo, github_repo_url, github_match, github_evidence}
    for one audit row against the candidate set."""
    script_id = project.get("script_id") or ""

    # Curated mapping is user-asserted: confirmed, and checked first.
    if mapping and script_id in mapping:
        entry = mapping[script_id]
        url = entry["url"] or (
            "https://github.com/" + entry["repo"] if "/" in entry["repo"] else ""
        )
        return {
            "github_repo": entry["repo"], "github_repo_url": url,
            "github_match": "confirmed", "github_evidence": "curated mapping",
        }

    best: dict[str, Any] | None = None  # {tier, score, candidate, evidence[]}
    for cand in candidates:
        evidence: list[str] = []
        tier = "none"
        score = 0

        if script_id and script_id in cand["clasp_script_ids"]:
            tier = "confirmed"
            evidence.append("scriptId found in .clasp.json")
            score += 100
        elif _explicit_hit(project, cand):
            tier = "confirmed"
            evidence.append("repo referenced in project description/source")
            score += 90

        exact, fuzzy = _name_signals(project.get("project_name") or "", cand["name"])
        shared, ratio = _function_overlap(project, cand)
        if exact:
            evidence.append("name match")
            score += 30
        elif fuzzy:
            evidence.append("similar name")
            score += 10
        if cand["has_appsscript_json"]:
            evidence.append("repo contains appsscript.json")
            score += 15
        if shared:
            pf_count = len(
                {f.lower() for f in project.get("function_names") or []} - COMMON_FUNCTIONS
            )
            evidence.append(f"{shared}/{pf_count} function names overlap")
            score += shared * 5 + (10 if ratio >= 0.5 else 0)

        if tier != "confirmed":
            strong_functions = shared >= 3 and ratio >= 0.6
            if exact and (cand["has_appsscript_json"] or shared >= 2 or ratio >= 0.5):
                tier = "probable"
            elif strong_functions and (cand["has_appsscript_json"] or fuzzy):
                tier = "probable"
            elif exact or (fuzzy and cand["has_appsscript_json"]) or shared >= 2:
                tier = "possible"

        if tier == "none":
            continue
        key = (TIER_RANK[tier], score)
        if best is None or key > best["key"]:
            best = {"key": key, "tier": tier, "candidate": cand, "evidence": evidence}

    if best is None:
        return {
            "github_repo": "", "github_repo_url": "",
            "github_match": "none",
            "github_evidence": "no evidence in searched candidates",
        }
    cand = best["candidate"]
    return {
        "github_repo": cand["full_name"],
        "github_repo_url": cand["html_url"],
        "github_match": best["tier"],
        "github_evidence": "; ".join(best["evidence"]),
    }


def enrich_rows(
    rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    mapping: dict[str, dict[str, str]] | None = None,
    explicit_texts: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Set the four github_* fields on every audit row, in place.
    explicit_texts maps scriptId -> text the project carries (e.g. its
    Drive description) for the explicit-reference confirmed signal."""
    explicit_texts = explicit_texts or {}
    for row in rows:
        project = dict(row)
        if row.get("script_id") in explicit_texts:
            project["explicit_text"] = explicit_texts[row["script_id"]]
        row.update(match_project(project, candidates, mapping))
    return rows
