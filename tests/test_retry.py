"""Tests for retry.execute_with_retry: 429/5xx backoff behaviour with a
fake request object and an injected sleeper (no real waiting, no network).
"""

import unittest

from gas_auditor.retry import execute_with_retry


class FakeHttpError(Exception):
    """Mimics googleapiclient.errors.HttpError's shape (resp.status)."""

    def __init__(self, status, headers=None):
        super().__init__(f"HttpError {status}")
        self.resp = _Resp(status, headers or {})


class _Resp:
    def __init__(self, status, headers):
        self.status = status
        self._headers = headers

    def get(self, name):
        return self._headers.get(name)


class FlakyRequest:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    def execute(self):
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class TestRetry(unittest.TestCase):
    def setUp(self):
        self.sleeps: list[float] = []

    def _run(self, request, **kw):
        return execute_with_retry(
            request, sleeper=self.sleeps.append, **kw
        )

    def test_success_first_try_no_sleep(self):
        req = FlakyRequest([{"ok": True}])
        self.assertEqual(self._run(req), {"ok": True})
        self.assertEqual(req.calls, 1)
        self.assertEqual(self.sleeps, [])

    def test_429_then_success_retries_with_backoff(self):
        req = FlakyRequest([FakeHttpError(429), FakeHttpError(429), {"ok": 1}])
        self.assertEqual(self._run(req, base_delay=2.0), {"ok": 1})
        self.assertEqual(req.calls, 3)
        self.assertEqual(len(self.sleeps), 2)
        # Exponential: ~2s then ~4s (plus <1s jitter).
        self.assertTrue(2.0 <= self.sleeps[0] < 3.0)
        self.assertTrue(4.0 <= self.sleeps[1] < 5.0)

    def test_503_is_retryable(self):
        req = FlakyRequest([FakeHttpError(503), {"ok": 1}])
        self.assertEqual(self._run(req), {"ok": 1})

    def test_403_raises_immediately(self):
        req = FlakyRequest([FakeHttpError(403), {"ok": 1}])
        with self.assertRaises(FakeHttpError):
            self._run(req)
        self.assertEqual(req.calls, 1)
        self.assertEqual(self.sleeps, [])

    def test_exhaustion_reraises_last_error(self):
        req = FlakyRequest([FakeHttpError(429)] * 10)
        with self.assertRaises(FakeHttpError):
            self._run(req, max_retries=2)
        self.assertEqual(req.calls, 3)  # initial + 2 retries

    def test_retry_after_header_wins(self):
        req = FlakyRequest([
            FakeHttpError(429, {"retry-after": "30"}), {"ok": 1},
        ])
        self.assertEqual(self._run(req, base_delay=2.0), {"ok": 1})
        self.assertTrue(30.0 <= self.sleeps[0] < 31.0)

    def test_plain_exception_without_status_raises(self):
        req = FlakyRequest([ValueError("boom")])
        with self.assertRaises(ValueError):
            self._run(req)
        self.assertEqual(req.calls, 1)


if __name__ == "__main__":
    unittest.main()
