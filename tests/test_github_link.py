"""Tests for the GitHub-association spike: tiered matcher, candidate
loaders (JSON inventory, curated mapping), and the local checkout scanner.
All offline -- fixtures only.
"""

import json
import tempfile
import unittest
from pathlib import Path

from gas_auditor.github_link import (
    enrich_rows,
    load_candidates,
    load_candidates_json,
    load_mapping,
    match_project,
    normalize_name,
    scan_local_repos,
)


def project(**over):
    base = {
        "script_id": "SID1",
        "project_name": "Invoice Bot",
        "function_names": ["buildInvoice", "sendInvoice", "logRun", "onOpen"],
    }
    base.update(over)
    return base


def candidate(**over):
    base = {
        "name": "invoice-bot", "full_name": "justin/invoice-bot",
        "html_url": "https://github.com/justin/invoice-bot",
        "description": "", "clasp_script_ids": [],
        "has_appsscript_json": False, "file_names": [], "function_names": [],
    }
    base.update(over)
    return base


class TestTiers(unittest.TestCase):
    def test_clasp_script_id_is_confirmed(self):
        m = match_project(project(), [candidate(clasp_script_ids=["SID1"])])
        self.assertEqual(m["github_match"], "confirmed")
        self.assertIn(".clasp.json", m["github_evidence"])
        self.assertEqual(m["github_repo"], "justin/invoice-bot")

    def test_mapping_is_confirmed_and_wins(self):
        mapping = {"SID1": {"repo": "justin/curated", "url": ""}}
        m = match_project(
            project(), [candidate(clasp_script_ids=["SID1"])], mapping
        )
        self.assertEqual(m["github_match"], "confirmed")
        self.assertEqual(m["github_repo"], "justin/curated")
        self.assertEqual(m["github_evidence"], "curated mapping")

    def test_explicit_text_is_confirmed(self):
        p = project(explicit_text="Source: https://github.com/justin/invoice-bot")
        m = match_project(p, [candidate(name="something-else",
                                        full_name="justin/invoice-bot")])
        self.assertEqual(m["github_match"], "confirmed")

    def test_name_plus_appsscript_is_probable(self):
        m = match_project(project(), [candidate(has_appsscript_json=True)])
        self.assertEqual(m["github_match"], "probable")

    def test_name_plus_function_overlap_is_probable(self):
        m = match_project(project(), [candidate(
            function_names=["buildInvoice", "sendInvoice", "other"])])
        self.assertEqual(m["github_match"], "probable")
        self.assertIn("function names overlap", m["github_evidence"])

    def test_name_alone_is_possible(self):
        m = match_project(project(), [candidate()])
        self.assertEqual(m["github_match"], "possible")

    def test_generic_title_never_matches_by_name(self):
        m = match_project(
            project(project_name="Test", function_names=[]),
            [candidate(name="test")],
        )
        self.assertEqual(m["github_match"], "none")
        self.assertEqual(m["github_repo"], "")

    def test_unrelated_is_none(self):
        m = match_project(project(), [candidate(
            name="weather-app", full_name="justin/weather-app",
            function_names=["fetchForecast"])])
        self.assertEqual(m["github_match"], "none")
        self.assertIn("no evidence", m["github_evidence"])

    def test_best_candidate_wins(self):
        weak = candidate()  # possible by name
        strong = candidate(
            name="invoice-bot-2", full_name="justin/invoice-bot-2",
            clasp_script_ids=["SID1"])  # confirmed by clasp
        m = match_project(project(), [weak, strong])
        self.assertEqual(m["github_repo"], "justin/invoice-bot-2")

    def test_common_functions_do_not_count(self):
        # Only shared function is onOpen (generic) + names differ -> none.
        m = match_project(
            project(project_name="Invoice Bot", function_names=["onOpen"]),
            [candidate(name="other", full_name="justin/other",
                       function_names=["onOpen", "doGet"])],
        )
        self.assertEqual(m["github_match"], "none")


class TestLoaders(unittest.TestCase):
    def test_json_flexible_shapes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "inv.json"
            p.write_text(json.dumps({"repos": [
                {"fullName": "justin/x", "url": "https://github.com/justin/x",
                 "clasp_script_id": "S9",
                 "files": ["appsscript.json", "Code.gs"],
                 "functions": ["doGet"]},
            ]}))
            (cand,) = load_candidates_json(p)
        self.assertEqual(cand["full_name"], "justin/x")
        self.assertEqual(cand["name"], "x")
        self.assertEqual(cand["clasp_script_ids"], ["S9"])
        self.assertTrue(cand["has_appsscript_json"])  # inferred from files
        self.assertEqual(cand["function_names"], ["doGet"])

    def test_mapping_shapes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "map.json"
            p.write_text(json.dumps({
                "S1": "justin/a",
                "S2": {"repo": "justin/b", "url": "https://example.invalid/b"},
            }))
            m = load_mapping(p)
        self.assertEqual(m["S1"], {"repo": "justin/a", "url": ""})
        self.assertEqual(m["S2"]["repo"], "justin/b")

    def test_load_candidates_dispatches_directory(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "myrepo"
            repo.mkdir()
            (repo / "appsscript.json").write_text("{}")
            cands = load_candidates(Path(td))
        self.assertEqual(len(cands), 1)
        self.assertTrue(cands[0]["has_appsscript_json"])


class TestLocalScanner(unittest.TestCase):
    def _make_repo(self, root: Path) -> Path:
        repo = root / "invoice-bot"
        (repo / ".git").mkdir(parents=True)
        (repo / ".git" / "config").write_text(
            '[remote "origin"]\n\turl = git@github.com:justin/invoice-bot.git\n'
        )
        (repo / ".clasp.json").write_text(json.dumps({"scriptId": "SID1"}))
        (repo / "appsscript.json").write_text("{}")
        (repo / "Code.gs").write_text(
            "function buildInvoice() {}\nfunction sendInvoice() {}\n"
        )
        (repo / "README.md").write_text("# Invoice Bot\n")
        return repo

    def test_scan_directory_of_repos(self):
        with tempfile.TemporaryDirectory() as td:
            self._make_repo(Path(td))
            (cand,) = scan_local_repos(Path(td))
        self.assertEqual(cand["full_name"], "justin/invoice-bot")
        self.assertEqual(cand["html_url"], "https://github.com/justin/invoice-bot")
        self.assertEqual(cand["clasp_script_ids"], ["SID1"])
        self.assertTrue(cand["has_appsscript_json"])
        self.assertEqual(
            sorted(cand["function_names"]), ["buildInvoice", "sendInvoice"]
        )
        self.assertTrue(cand["local_path"].endswith("invoice-bot"))
        self.assertTrue(cand["readme_path"].endswith("README.md"))

    def test_scanned_repo_matches_project_as_confirmed(self):
        with tempfile.TemporaryDirectory() as td:
            self._make_repo(Path(td))
            cands = scan_local_repos(Path(td))
        m = match_project(project(), cands)
        self.assertEqual(m["github_match"], "confirmed")


class TestEnrichRows(unittest.TestCase):
    def test_enrich_sets_all_fields_and_uses_explicit_texts(self):
        rows = [project(), project(script_id="SID2", project_name="Other")]
        enrich_rows(
            rows, [candidate(clasp_script_ids=["SID1"])],
            explicit_texts={"SID2": "see https://github.com/justin/invoice-bot"},
        )
        self.assertEqual(rows[0]["github_match"], "confirmed")
        # SID2: explicit text names the candidate -> confirmed too
        self.assertEqual(rows[1]["github_match"], "confirmed")
        self.assertEqual(rows[1]["github_repo"], "justin/invoice-bot")

    def test_normalize_name(self):
        self.assertEqual(normalize_name("My-App_Script 2"), "myappscript2")


if __name__ == "__main__":
    unittest.main()
