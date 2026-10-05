"""Native complete-provider schema depth differs from untrusted policy input."""
import unittest

from intune_iac.io import AppError, MAX_BYTES, parse_json, parse_provider_schema_json


class ProviderSchemaJSONTests(unittest.TestCase):
    @staticmethod
    def nested(depth):
        return b'[' * depth + b'0' + b']' * depth

    def test_general_input_depth_remains_64(self):
        parse_json(self.nested(64))
        with self.assertRaises(AppError):
            parse_json(self.nested(65))

    def test_native_schema_admits_observed_depth_and_fixed_upper_boundary(self):
        for depth in (71, 96):
            with self.subTest(depth=depth):
                parse_provider_schema_json(self.nested(depth))
        with self.assertRaises(AppError):
            parse_provider_schema_json(self.nested(97))

    def test_schema_retains_strict_json_safeguards(self):
        for payload in (b'{"a":0,"a":1}', b'{"a":NaN}', b'{"a":Infinity}',
                        b'{"a":-Infinity}', b'{"a":1e309}', b'{"a":9007199254740992}',
                        b'{"a":"\\ud800"}', b'{"a":'):
            with self.subTest(payload=payload), self.assertRaises(AppError):
                parse_provider_schema_json(payload)

    def test_schema_bytes_limit_and_type_are_enforced_before_decoding(self):
        for payload in (b' ' * (MAX_BYTES + 1), '{}', None):
            with self.subTest(kind=type(payload).__name__), self.assertRaises(AppError) as error:
                parse_provider_schema_json(payload)
            self.assertEqual(error.exception.code, 'provider_schema_size')

    def test_legitimate_unicode_numbers_and_empty_values_are_preserved(self):
        self.assertEqual(parse_provider_schema_json(
            b'{"name":"caf\\u00e9","max":9007199254740991,"none":null,"empty":[]}'),
            {'name': 'caf\u00e9', 'max': 9007199254740991, 'none': None, 'empty': []})


if __name__ == '__main__':
    unittest.main()
