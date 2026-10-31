"""Tests for the shared scan pipeline (pipeline.run_scan), the sequence
both the CLI and the dashboard delegate to. Fake Drive/Script services
via the `services` seam -- no credentials, no network."""

import tempfile
import unittest
from pathlib import Path

from fixtures import FakeScript

from gas_auditor.pipeline import ScanOptions, run_scan


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


LISTED = [{
    "id": "S1", "name": "Standalone",
    "owners": [{"emailAddress": "me@example.com"}],
}]


def _options(tmp, **kwargs):
    kwargs.setdefault("state_path", Path(tmp) / "state.json")
    return ScanOptions(
        credentials_path=Path("credentials.json"),
        token_path=Path("token.json"),
        **kwargs,
    )


class TestPipeline(unittest.TestCase):
    def test_full_run_writes_state_and_ids_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            ids_out = Path(tmp) / "ids.txt"
            rows = run_scan(
                _options(tmp, script_ids_out=ids_out),
                services=(_Drive(LISTED, {}), FakeScript()),
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["script_id"], "S1")
            # Tracking stamped the row from the state it just wrote.
            self.assertTrue(rows[0]["first_seen"])
            self.assertEqual(rows[0]["first_seen"], rows[0]["last_seen"])
            self.assertIn("S1", ids_out.read_text(encoding="utf-8"))

    def test_state_seeds_next_run(self):
        """A project found once stays audited even after Drive listing
        stops returning it -- the container-bound seed-and-remember path,
        exercised end to end through the pipeline."""
        import json

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            first_rows = run_scan(
                _options(tmp, state_path=state_path),
                services=(_Drive(LISTED, {}), FakeScript()),
            )
            first_seen = first_rows[0]["first_seen"]
            # Second run: Drive lists nothing, but the state-known ID is
            # re-fetched by files.get and audited again.
            rows = run_scan(
                _options(tmp, state_path=state_path),
                services=(_Drive([], {"S1": LISTED[0]}), FakeScript()),
            )
            self.assertEqual([r["script_id"] for r in rows], ["S1"])
            # first_seen is stable across runs; only last_seen advances.
            self.assertEqual(rows[0]["first_seen"], first_seen)
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["projects"]["S1"]["times_seen"], 2)
            self.assertEqual(saved["projects"]["S1"]["status"], "active")

    def test_progress_callback_and_no_state(self):
        seen = []
        with tempfile.TemporaryDirectory() as tmp:
            rows = run_scan(
                _options(
                    tmp, state_path=None,
                    on_project=lambda i, n, f: seen.append((i, n, f["id"])),
                ),
                services=(_Drive(LISTED, {}), FakeScript()),
            )
        self.assertEqual(seen, [(1, 1, "S1")])
        self.assertEqual(len(rows), 1)
        # No state file, no tracking stamps.
        self.assertEqual(rows[0]["first_seen"], "")
        self.assertFalse((Path(tmp) / "state.json").exists())


if __name__ == "__main__":
    unittest.main()
