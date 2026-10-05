"""Focused regressions for the offline materials verifier's acquired formats."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import unittest

from jsonschema.exceptions import SchemaError


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("material_verifier", ROOT / "tools/verify-materials.py")
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)

ACQUISITION_SHA256 = "bb6a3022e99c52fe995db5c273c333d6a9afc88a8bf58fc8e76ba8a27b465889"
BOM_SHA256 = "3e92dddbc30cf7f6a02b80f0942b1a4cfd4fb1c26f1dfc4310afa9d613cafb93"


class SchemaDialectTests(unittest.TestCase):
    def test_declared_draft07_accepts_tuple_items(self):
        VERIFIER.check_json_schema({"$schema": "http://json-schema.org/draft-07/schema#",
                                    "type": "array", "items": [{"type": "string"}]})

    def test_declared_draft202012_rejects_tuple_items(self):
        with self.assertRaises(SchemaError):
            VERIFIER.check_json_schema({"$schema": "https://json-schema.org/draft/2020-12/schema",
                                        "type": "array", "items": [{"type": "string"}]})

    def test_unknown_declared_dialect_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Unknown JSON Schema dialect"):
            VERIFIER.check_json_schema({"$schema": "https://example.invalid/schema"})

    def test_malformed_declared_dialect_fails_closed(self):
        for dialect in (None, 7, [], {}):
            with self.subTest(dialect=dialect), self.assertRaises(ValueError):
                VERIFIER.check_json_schema({"$schema": dialect})

    def test_missing_dialect_retains_draft202012_policy(self):
        VERIFIER.check_json_schema({"type": "array", "prefixItems": [{"type": "string"}]})
        with self.assertRaises(SchemaError):
            VERIFIER.check_json_schema({"type": "array", "items": [{"type": "string"}]})

    def test_boolean_schemas_remain_valid(self):
        VERIFIER.check_json_schema(True)
        VERIFIER.check_json_schema(False)

    def test_acquired_bom_is_unmodified_and_valid_in_its_dialect(self):
        raw = (ROOT / "research/enterprise-dependencies/bom-1.6.schema.json").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), BOM_SHA256)
        VERIFIER.check_json_schema(VERIFIER.parse_json(raw.decode("utf-8")))


class MaterialJsonFormatTests(unittest.TestCase):
    def test_stream_accepts_pretty_printed_whitespace_separated_objects(self):
        self.assertEqual(VERIFIER.parse_jsonstream(' \n{\n"a": 1\n}\t\r\n{"b": [2]}\n'),
                         [{"a": 1}, {"b": [2]}])

    def test_stream_requires_separator_between_records(self):
        for raw in ('{}{}', 'truefalse', '1{}', '{}\u00a0{}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                VERIFIER.parse_jsonstream(raw)

    def test_stream_rejects_malformed_records_and_trailing_junk(self):
        for raw in ('{"a":', '{} {"b":', '{} trailing', '{} , {}', '{} \n[1,]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                VERIFIER.parse_jsonstream(raw)

    def test_stream_rejects_duplicate_keys_in_any_record_or_nested_object(self):
        for raw in ('{"a": 1, "a": 2}', '{} {"nested": {"a": 1, "a": 2}}'):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
                VERIFIER.parse_jsonstream(raw)

    def test_all_json_formats_reject_nonfinite_literals_and_overflow(self):
        for parse in (VERIFIER.parse_json, VERIFIER.parse_jsonl, VERIFIER.parse_jsonstream):
            for number in ('NaN', 'Infinity', '-Infinity', '1e999', '-1e999'):
                raw = '{"number": ' + number + '}'
                with self.subTest(parser=parse.__name__, number=number):
                    with self.assertRaisesRegex(ValueError, "Nonfinite JSON number"):
                        parse(raw)

    def test_jsonl_preserves_complete_record_per_line_rule(self):
        self.assertEqual(VERIFIER.parse_jsonl('\n{"a":1}\n \n{"b":2}\n'),
                         [{"a": 1}, {"b": 2}])
        for raw in ('{\n"a": 1\n}', '{} {}\n', '{"a":1,"a":2}\n'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                VERIFIER.parse_jsonl(raw)

    def test_stream_allows_blank_input_like_jsonl(self):
        self.assertEqual(VERIFIER.parse_jsonstream(' \t\r\n'), [])

    def test_acquisition_is_byte_preserved_stream_and_remains_invalid_jsonl(self):
        raw = (ROOT / "research/provider-qualification/evidence/module-acquisition.jsonstream").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), ACQUISITION_SHA256)
        records = VERIFIER.parse_jsonstream(raw.decode("utf-8"))
        self.assertGreater(len(records), 1)
        self.assertTrue(all(isinstance(record, dict) and "Path" in record for record in records))
        with self.assertRaises(ValueError):
            VERIFIER.parse_jsonl(raw.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
