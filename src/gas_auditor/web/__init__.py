"""Optional Flask + Jinja2 web dashboard for gas_auditor.

A presentation layer over the unchanged core (auth/discovery/audit/output):
nothing in this subpackage is imported by gas_auditor's top-level package,
so the CLI and library work without Flask installed.

    pip install -e ".[web]"
    gas-audit-web            # http://127.0.0.1:5001

Modules:
    viewmodels.py  pure display logic (status wording, scope names) -- no I/O
    templates/     Jinja2: base.html, index.html, fragments/ (HTMX partials)
    service.py     background scan job (thread + state) over the core modules
    app.py         create_app() Flask factory, routes, server entry point
"""

from __future__ import annotations

from .app import create_app
from .service import ScanService, make_default_runner

__all__ = ["ScanService", "create_app", "make_default_runner"]
