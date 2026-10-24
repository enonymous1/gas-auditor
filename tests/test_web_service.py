"""ScanService tests: background execution, state transitions, single-flight."""

import time
import unittest

from gas_auditor.web.service import ScanService


def _wait_done(svc: ScanService, timeout: float = 5.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = svc.snapshot().status
        if status in ("done", "error"):
            return status
        time.sleep(0.02)
    raise AssertionError("scan did not finish in time")


class TestScanService(unittest.TestCase):
    def test_success(self):
        svc = ScanService(lambda: [{"project_name": "X"}])
        self.assertEqual(svc.snapshot().status, "idle")
        self.assertTrue(svc.start())
        self.assertEqual(_wait_done(svc), "done")
        snap = svc.snapshot()
        self.assertEqual(snap.rows, [{"project_name": "X"}])
        self.assertTrue(snap.finished_at)

    def test_failure_lands_in_state(self):
        def boom():
            raise RuntimeError("no credentials")

        svc = ScanService(boom)
        svc.start()
        self.assertEqual(_wait_done(svc), "error")
        self.assertIn("no credentials", svc.snapshot().error)

    def test_single_flight(self):
        # Runner blocks on an Event so the first scan is *guaranteed* still
        # running when the second start() is attempted (no timing race).
        import threading

        release = threading.Event()
        calls = []

        def runner():
            calls.append(1)
            release.wait(timeout=5)
            return []

        svc = ScanService(runner)
        self.assertTrue(svc.start())
        self.assertFalse(svc.start())  # already running -> no-op
        release.set()
        self.assertEqual(_wait_done(svc), "done")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
