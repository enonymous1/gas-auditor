"""Freeze tests: run scripts/freeze.py as a subprocess and check the
static site it produces. Skipped without the web extra (Flask), exactly
like the other web tests."""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import flask  # noqa: F401 -- import check only
except ImportError:
    flask = None

REPO_ROOT = Path(__file__).resolve().parent.parent

DEMO_IDS = [
    "demo-sheet-helper-001",
    "demo-standalone-tool-002",
    "demo-bound-script-003",
    "demo-quiet-addon-004",
    "demo-failing-project-005",
    "demo-docs-automator-006",
]


@unittest.skipIf(flask is None, "Flask not installed (web extra)")
class TestFreeze(unittest.TestCase):
    def test_freeze_produces_static_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "freeze-site"
            env = dict(os.environ)
            env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get(
                "PYTHONPATH", ""
            )
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "freeze.py"),
                 "--output", str(out)],
                capture_output=True, text=True, cwd=REPO_ROOT, env=env,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            expected = (
                ["index.html", "scopes.html", "gas_audit.csv",
                 "gas_script_ids.txt"]
                + [f"project-{sid}.html" for sid in DEMO_IDS]
            )
            for name in expected:
                self.assertTrue((out / name).exists(), name)

            index = (out / "index.html").read_text(encoding="utf-8")
            # Demo content present, banner present, no live hooks left.
            self.assertIn("Demo Sheet Helper", index)
            self.assertIn("Static demo", index)
            self.assertNotIn('hx-get="/api/scan"', index)
            self.assertNotIn('href="/project/', index)
            self.assertNotIn("script.google.com/home/projects", index)
            for sid in DEMO_IDS:
                self.assertIn(f'href="project-{sid}.html"', index)
            # Every project link in the index resolves to a written file,
            # and every scope-chip link resolves to an anchor on scopes.
            scopes = (out / "scopes.html").read_text(encoding="utf-8")
            for href in re.findall(r'href="(project-[^"]+|scopes\.html#[^"]+)"',
                                   index):
                if href.startswith("project-"):
                    self.assertTrue((out / href).exists(), href)
                else:
                    anchor = href.split("#", 1)[1]
                    self.assertIn(f'id="{anchor}"', scopes, href)

            detail = (out / "project-demo-failing-project-005.html").read_text(
                encoding="utf-8"
            )
            self.assertIn("does not have permission", detail)
            self.assertIn('href="index.html"', detail)

            csv_text = (out / "gas_audit.csv").read_text(encoding="utf-8")
            self.assertTrue(csv_text.startswith("project_name,script_id,"))
            self.assertIn("demo-sheet-helper-001", csv_text)
            ids_text = (out / "gas_script_ids.txt").read_text(encoding="utf-8")
            for sid in DEMO_IDS:
                self.assertIn(sid, ids_text)


if __name__ == "__main__":
    unittest.main()
