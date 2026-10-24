import unittest

from gas_auditor.metrics import summarise_metrics
from gas_auditor.processes import summarise_processes

from fixtures import METRICS, PROCESSES


class TestMetrics(unittest.TestCase):
    def test_summarise(self):
        # active users: latest interval only (5, not 3+5 -- not additive)
        self.assertEqual(
            summarise_metrics(METRICS),
            {"active_users_latest": 5, "total_executions": 17,
             "failed_executions": 3},
        )

    def test_empty(self):
        self.assertEqual(
            summarise_metrics({}),
            {"active_users_latest": 0, "total_executions": 0,
             "failed_executions": 0},
        )


class TestProcesses(unittest.TestCase):
    def test_summarise(self):
        p = summarise_processes(PROCESSES)
        self.assertEqual(p["recent_process_count"], 3)
        self.assertEqual(p["failed_process_count"], 2)  # FAILED + TIMED_OUT
        self.assertEqual(p["process_types"], {"TIME_DRIVEN": 2, "WEBAPP": 1})
        self.assertEqual(p["last_execution_function"], "doGet")
        self.assertEqual(p["last_execution_status"], "FAILED")

    def test_empty(self):
        p = summarise_processes([])
        self.assertEqual(p["recent_process_count"], 0)
        self.assertEqual(p["last_execution_time"], "")


if __name__ == "__main__":
    unittest.main()
