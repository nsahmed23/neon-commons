"""Independent coverage counterexamples; no live Graph traffic."""
import json
from pathlib import Path
import tempfile
import unittest

from intune_iac.capture import capture, GRAPH_ROOT


TENANT = "11111111-1111-4111-8111-111111111111"
POLICY = "22222222-2222-4222-8222-222222222222"
ASSIGNMENT = "abcdefab-cdef-4abc-8def-abcdefabcdef"


class CaptureAuditTests(unittest.TestCase):
    def collect(self, settings=None, assignments=None, extra=None):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "capture"
            settings_root = GRAPH_ROOT + "/" + POLICY + "/settings"
            assignments_root = GRAPH_ROOT + "/" + POLICY + "/assignments"
            responses = {GRAPH_ROOT: {"value": [{"id": POLICY}]},
                         settings_root: settings if settings is not None else {"value": []},
                         assignments_root: assignments if assignments is not None else {"value": []}}
            responses.update(extra or {})
            result = capture(TENANT, POLICY, output,
                             transport=lambda url: (200, json.dumps(responses[url]).encode()))
            exported = json.loads((output / "export.json").read_text())
            return result, exported

    def test_case_variant_assignment_uuid_is_duplicate_but_raw_case_survives(self):
        rows = [{"id": ASSIGNMENT}, {"id": ASSIGNMENT.upper()}]
        result, exported = self.collect(assignments={"value": rows})
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["coverage"][2]["reason"], "duplicate_record_identity")
        self.assertEqual(exported["collections"][2]["pages"][0]["body"]["value"], rows)

    def test_declared_total_must_match_complete_chain(self):
        for count in (1, "0", True, -1):
            with self.subTest(count=count):
                result, _ = self.collect(assignments={"value": [], "@odata.count": count})
                self.assertEqual(result["status"], "partial")
                self.assertIn(result["coverage"][2]["reason"],
                              {"invalid_collection_count", "collection_count_mismatch"})

    def test_all_page_counts_apply_to_total_not_page_length(self):
        root = GRAPH_ROOT + "/" + POLICY + "/settings"
        next_link = root + "?$skiptoken=NEXT"
        first = {"value": [{"id": "0"}], "@odata.count": 2, "@odata.nextLink": next_link}
        result, _ = self.collect(settings=first, extra={next_link: {"value": [{"id": "1"}], "@odata.count": 1}})
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["coverage"][1]["reason"], "collection_count_mismatch")
        result, _ = self.collect(settings=first, extra={next_link: {"value": [{"id": "1"}], "@odata.count": 2}})
        self.assertEqual(result["status"], "captured")

    def test_missing_or_empty_record_identity_cannot_be_complete(self):
        for row in ({}, {"id": None}, {"id": 1}, {"id": ""}):
            with self.subTest(row=row):
                result, _ = self.collect(settings={"value": [row]})
                self.assertEqual(result["status"], "partial")
                self.assertEqual(result["coverage"][1]["reason"], "missing_record_identity")

    def test_opaque_setting_identity_is_case_sensitive(self):
        result, _ = self.collect(settings={"value": [{"id": "opaque-A"}, {"id": "opaque-a"}]})
        self.assertEqual(result["status"], "captured")


if __name__ == "__main__":
    unittest.main()
