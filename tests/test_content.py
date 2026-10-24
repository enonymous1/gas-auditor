import unittest

from gas_auditor.content import parse_manifest, summarise_content

from fixtures import CONTENT


class TestContent(unittest.TestCase):
    def test_file_stats(self):
        s = summarise_content(CONTENT)
        self.assertEqual(s["file_count"], 3)
        self.assertEqual(s["server_js_count"], 1)
        self.assertEqual(s["html_count"], 1)
        self.assertEqual(s["json_count"], 1)
        self.assertEqual(
            s["file_counts_by_type"], {"SERVER_JS": 1, "HTML": 1, "JSON": 1}
        )

    def test_functions(self):
        s = summarise_content(CONTENT)
        self.assertEqual(s["function_names"], ["a", "b"])
        self.assertEqual(s["function_count"], 2)

    def test_manifest(self):
        s = summarise_content(CONTENT)
        self.assertEqual(s["oauth_scope_count"], 1)
        self.assertTrue(s["has_webapp"])
        self.assertFalse(s["has_execution_api"])
        self.assertEqual(s["advanced_services"], ["Drive (serviceId=drive, v2)"])
        self.assertEqual(s["manifest_time_zone"], "America/New_York")
        self.assertEqual(s["runtime_version"], "V8")

    def test_no_manifest(self):
        out = parse_manifest([{"name": "Code", "type": "SERVER_JS", "source": "x"}])
        self.assertEqual(out["oauth_scopes"], [])
        self.assertFalse(out["has_webapp"])

    def test_invalid_manifest_json_is_skipped(self):
        out = parse_manifest(
            [{"name": "appsscript", "type": "JSON", "source": "{not json"}]
        )
        self.assertEqual(out["oauth_scopes"], [])


if __name__ == "__main__":
    unittest.main()
