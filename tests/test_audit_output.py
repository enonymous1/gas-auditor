import tempfile
import unittest
from pathlib import Path

from gas_auditor import audit_project, export_csv, to_dataframe
from gas_auditor.config import AUDIT_FIELDS

from fixtures import DRIVE_FILE, FakeScript


class TestAuditProject(unittest.TestCase):
    def _row(self):
        return audit_project(
            DRIVE_FILE, FakeScript(),
            metrics_granularity="WEEKLY",
            process_limit=50, process_since_days=None,
        )

    def test_row_shape_and_values(self):
        row = self._row()
        self.assertEqual(set(row), set(AUDIT_FIELDS))
        self.assertEqual(row["project_name"], "T")  # projects.get title wins
        self.assertEqual(row["parent_id"], "PARENT1")
        self.assertEqual(row["total_executions"], 4)
        self.assertEqual(row["failed_executions"], 1)
        for col in ("project_error", "content_error",
                    "metrics_error", "processes_error"):
            self.assertEqual(row[col], "", col)

    def test_csv_flattening(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.csv"
            export_csv([self._row()], out)
            text = out.read_text(encoding="utf-8")
        self.assertIn("TRIGGER=1", text)
        self.assertIn("SERVER_JS=1", text)

    def test_dataframe(self):
        df = to_dataframe([self._row()])
        self.assertEqual(df.shape, (1, len(AUDIT_FIELDS)))
        self.assertEqual(df["total_executions"][0], 4)


class BrokenScript(FakeScript):
    def getContent(self, scriptId):
        raise RuntimeError("boom")


class TestErrorIsolation(unittest.TestCase):
    def test_one_stage_failure_does_not_abort_row(self):
        row = audit_project(
            DRIVE_FILE, BrokenScript(),
            metrics_granularity="WEEKLY",
            process_limit=50, process_since_days=None,
        )
        self.assertIn("boom", row["content_error"])
        self.assertEqual(row["metrics_error"], "")
        self.assertEqual(row["total_executions"], 4)  # other stages still ran


if __name__ == "__main__":
    unittest.main()
