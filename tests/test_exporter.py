"""Exporter tests: offline, FakeScript + temp dirs."""

import json
import tempfile
import unittest
from pathlib import Path

from gas_auditor.exporter import (
    export_project,
    export_projects,
    project_dirname,
    slugify,
    write_project_files,
)

from fixtures import CONTENT, FakeScript


class _BadScript:
    def projects(self):
        return self

    def get(self, scriptId):
        raise RuntimeError("boom")

    def getContent(self, scriptId):
        raise RuntimeError("boom")


META = {
    "script_id": "ABC123456789",
    "title": "My Project!",
    "parent_id": "PARENT1",
    "creator_email": "me@example.com",
    "last_modify_user_email": "me@example.com",
    "project_create_time": "2024-01-01T00:00:00Z",
    "project_update_time": "2026-01-01T00:00:00Z",
}


class TestNaming(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("Crypto - Gemini - Candles"), "Crypto-Gemini-Candles")
        self.assertEqual(slugify("  "), "untitled")
        self.assertEqual(slugify("208 Scan System"), "208-Scan-System")

    def test_dirname_has_id_suffix(self):
        self.assertEqual(
            project_dirname("Untitled project", "ABCDEFGHIJ"),
            "Untitled-project__ABCDEFGH",
        )


class TestWriteProjectFiles(unittest.TestCase):
    def test_files_extensions_manifest_and_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            r = write_project_files(META, CONTENT, Path(td))
            self.assertTrue(r.ok)
            # Folder suffix comes from the content payload's scriptId
            # (fixtures use "ABC"); project.json keeps the full ID set.
            d = Path(td) / "My-Project__ABC"
            self.assertEqual(r.directory, d)
            self.assertEqual(
                sorted(r.files_written),
                ["Code.js", "appsscript.json", "page.html"],
            )
            self.assertEqual((d / "Code.js").read_text(encoding="utf-8"),
                             "function a(){} function b(){}")
            snap = json.loads((d / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(snap["parent_id"], "PARENT1")
            self.assertIn("/ABC/edit", snap["editor_url"])
            self.assertEqual(len(snap["files"]), 3)

    def test_stale_files_reported_not_deleted(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "My-Project__ABC"
            d.mkdir(parents=True)
            (d / "Old.js").write_text("// gone upstream", encoding="utf-8")
            r = write_project_files(META, CONTENT, Path(td))
            self.assertEqual(r.stale_files, ["Old.js"])
            self.assertTrue((d / "Old.js").exists())


class TestExportProject(unittest.TestCase):
    def test_fetch_and_write_via_fake(self):
        with tempfile.TemporaryDirectory() as td:
            r = export_project(FakeScript(), "ABC", Path(td))
            self.assertTrue(r.ok, r.error)
            self.assertEqual(r.title, "T")  # FakeScript projects.get title
            self.assertEqual(len(r.files_written), 3)

    def test_error_is_captured_not_raised(self):
        with tempfile.TemporaryDirectory() as td:
            r = export_project(_BadScript(), "X", Path(td))
            self.assertFalse(r.ok)
            self.assertIn("boom", r.error)

    def test_batch_dedupes_and_isolates(self):
        with tempfile.TemporaryDirectory() as td:
            results = export_projects(FakeScript(), ["ABC", "ABC"], Path(td))
            self.assertEqual(len(results), 1)
            self.assertTrue(results[0].ok)


if __name__ == "__main__":
    unittest.main()
