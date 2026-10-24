"""Tests for discovery merging: Drive listing + seeded IDs (the
container-bound workaround). Fake Drive service, no network."""

import tempfile
import unittest
from pathlib import Path

from gas_auditor.discovery import (
    discover_projects,
    fetch_file_meta,
    format_script_ids,
    read_script_ids,
)


class _Req:
    def __init__(self, payload=None, error=None):
        self._payload = payload
        self._error = error

    def execute(self):
        if self._error:
            raise self._error
        return self._payload


class _Files:
    def __init__(self, listed, by_id):
        self._listed = listed
        self._by_id = by_id

    def list(self, **kwargs):
        return _Req({"files": list(self._listed)})

    def get(self, fileId, **kwargs):
        if fileId in self._by_id:
            return _Req(self._by_id[fileId])
        return _Req(error=RuntimeError("HttpError 404"))


class _Drive:
    def __init__(self, listed, by_id):
        self._files = _Files(listed, by_id)

    def files(self):
        return self._files


LISTED = [{"id": "S1", "name": "Standalone"}]
BOUND = {"id": "B1", "name": "Bound Sheet Script", "mimeType": "x"}


class TestDiscoveryMerge(unittest.TestCase):
    def test_extra_id_fetched_and_marked_seeded(self):
        drive = _Drive(LISTED, {"B1": BOUND})
        files = discover_projects(drive, extra_ids=["B1"])
        self.assertEqual([f["id"] for f in files], ["S1", "B1"])
        self.assertTrue(files[1]["_seeded"])

    def test_extra_id_already_listed_not_duplicated(self):
        drive = _Drive(LISTED, {"S1": LISTED[0]})
        files = discover_projects(drive, extra_ids=["S1"])
        self.assertEqual(len(files), 1)
        self.assertNotIn("_seeded", files[0])

    def test_unfetchable_extra_id_skipped_not_fatal(self):
        drive = _Drive(LISTED, {})
        files = discover_projects(drive, extra_ids=["GONE"])
        self.assertEqual([f["id"] for f in files], ["S1"])

    def test_no_extras_is_plain_listing(self):
        drive = _Drive(LISTED, {})
        self.assertEqual(len(discover_projects(drive)), 1)

    def test_fetch_file_meta_none_on_error(self):
        drive = _Drive([], {})
        self.assertIsNone(fetch_file_meta(drive, "NOPE"))
        drive2 = _Drive([], {"B1": BOUND})
        self.assertEqual(fetch_file_meta(drive2, "B1")["name"],
                         "Bound Sheet Script")


class TestScriptIdsFile(unittest.TestCase):
    def test_format_then_read_roundtrip(self):
        rows = [
            {"script_id": "S1", "project_name": "Standalone", "parent_id": ""},
            {"script_id": "B1", "project_name": "Bound One",
             "parent_id": "SHEET9"},
        ]
        text = format_script_ids(rows, extra_ids=["KEPT1", "S1"])
        self.assertIn("[bound to SHEET9]", text)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "ids.txt"
            p.write_text(text, encoding="utf-8")
            self.assertEqual(read_script_ids(p), ["S1", "B1", "KEPT1"])

    def test_read_tolerates_comments_and_blanks(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "ids.txt"
            p.write_text("# header\n\nABC123  # trailing note\n  \nDEF456\n",
                         encoding="utf-8")
            self.assertEqual(read_script_ids(p), ["ABC123", "DEF456"])


if __name__ == "__main__":
    unittest.main()
