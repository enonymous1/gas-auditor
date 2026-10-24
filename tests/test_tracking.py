"""Tests for cross-run tracking: first/last seen, missing detection,
returns, renames, the discovery-scope guard, and state persistence."""

import tempfile
import unittest
from pathlib import Path

from gas_auditor.tracking import (
    apply_state,
    describe_changes,
    empty_state,
    load_state,
    save_state,
    update_state,
)

T1 = "2026-10-21T00:00:00Z"
T2 = "2026-10-22T00:00:00Z"
T3 = "2026-10-23T00:00:00Z"


def row(sid, name):
    return {"script_id": sid, "project_name": name, "first_seen": "", "last_seen": ""}


class TestLifecycle(unittest.TestCase):
    def test_first_run_all_new(self):
        state = empty_state()
        rows = [row("A", "Alpha"), row("B", "Beta")]
        changes = update_state(state, rows, scope="my_drive", now=T1)
        self.assertEqual(sorted(changes["new"]), ["Alpha", "Beta"])
        apply_state(rows, state)
        self.assertEqual(rows[0]["first_seen"], T1)
        self.assertEqual(rows[0]["last_seen"], T1)

    def test_missing_then_returned(self):
        state = empty_state()
        update_state(state, [row("A", "Alpha"), row("B", "Beta")],
                     scope="my_drive", now=T1)
        # Run 2: B absent -> newly missing; last_seen stays at T1.
        changes = update_state(state, [row("A", "Alpha")],
                               scope="my_drive", now=T2)
        self.assertEqual(len(changes["newly_missing"]), 1)
        rec = state["projects"]["B"]
        self.assertEqual(rec["status"], "missing")
        self.assertEqual(rec["missing_since"], T2)
        self.assertEqual(rec["last_seen"], T1)
        # Run 3: B still absent -> still_missing, not newly missing.
        changes = update_state(state, [row("A", "Alpha")],
                               scope="my_drive", now=T3)
        self.assertEqual(changes["newly_missing"], [])
        self.assertEqual(changes["still_missing"], 1)
        # Run 4: B back -> returned, missing cleared, first_seen kept.
        rows = [row("A", "Alpha"), row("B", "Beta")]
        changes = update_state(state, rows, scope="my_drive", now=T3)
        self.assertEqual(changes["returned"], ["Beta"])
        rec = state["projects"]["B"]
        self.assertEqual(rec["status"], "active")
        self.assertEqual(rec["first_seen"], T1)
        self.assertEqual(rec["times_seen"], 2)

    def test_rename_detected_by_script_id(self):
        state = empty_state()
        update_state(state, [row("A", "Old Name")], scope="my_drive", now=T1)
        changes = update_state(state, [row("A", "New Name")],
                               scope="my_drive", now=T2)
        self.assertEqual(changes["renamed"], [("Old Name", "New Name")])
        self.assertEqual(changes["new"], [])
        self.assertEqual(state["projects"]["A"]["project_name"], "New Name")

    def test_scope_change_skips_missing_marking(self):
        state = empty_state()
        update_state(state, [row("A", "Alpha"), row("S", "Shared")],
                     scope="all_drives", now=T1)
        changes = update_state(state, [row("A", "Alpha")],
                               scope="my_drive", now=T2)
        self.assertTrue(changes["scope_changed"])
        self.assertEqual(changes["newly_missing"], [])
        self.assertEqual(state["projects"]["S"]["status"], "active")
        # Next run at the new scope: missing-marking resumes.
        changes = update_state(state, [row("A", "Alpha")],
                               scope="my_drive", now=T3)
        self.assertEqual(len(changes["newly_missing"]), 1)

    def test_describe_changes_mentions_missing(self):
        state = empty_state()
        update_state(state, [row("A", "Alpha"), row("B", "Beta")],
                     scope="my_drive", now=T1)
        changes = update_state(state, [row("A", "Alpha")],
                               scope="my_drive", now=T2)
        lines = describe_changes(changes)
        self.assertTrue(any("MISSING" in l and "Beta" in l for l in lines))


class TestPersistence(unittest.TestCase):
    def test_roundtrip_and_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            self.assertEqual(load_state(path), empty_state())
            state = empty_state()
            update_state(state, [row("A", "Alpha")], scope="my_drive", now=T1)
            save_state(path, state)
            loaded = load_state(path)
        self.assertEqual(loaded["projects"]["A"]["first_seen"], T1)

    def test_corrupt_state_warns_and_starts_fresh(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertLogs("gas_auditor.tracking", level="WARNING"):
                state = load_state(path)
        self.assertEqual(state, empty_state())


if __name__ == "__main__":
    unittest.main()
