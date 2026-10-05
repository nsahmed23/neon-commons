"""The inactive PowerShell preview must reject arguments its binder loses."""
import unittest

from reference.core import render_powershell


class PowerShellPreviewTests(unittest.TestCase):
    def test_reserved_stop_parsing_argument_is_rejected(self):
        # Actual Linux PowerShell 7.6.6 drops this value even in a quoted,
        # splatted Standard-mode array. Reject the entire proposal before loss.
        for arguments in (['--%'], ['before', '--%', 'after'], ['', '--%']):
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(ValueError, 'reserved.*--%'):
                    render_powershell('python', arguments)

    def test_unicode_single_quote_delimiters_are_rejected(self):
        for codepoint in range(0x2018, 0x201c):
            for value in (chr(codepoint), 'A' + chr(codepoint) + 'B'):
                with self.subTest(codepoint=hex(codepoint), value=value):
                    with self.assertRaisesRegex(ValueError, 'Unicode single-quote delimiters'):
                        render_powershell('python', [value])

    def test_normal_unicode_and_double_quotes_remain_literal(self):
        for value in ('café', '日本語', 'A“B', 'A”B', 'A‧B'):
            with self.subTest(value=value):
                self.assertIn("'" + value + "'", render_powershell('python', [value]))

    def test_nearby_literal_values_remain_supported(self):
        for value in ('--', '--%%', 'x--%', '--%x', ' --%', '--% ', '--% value'):
            with self.subTest(value=value):
                self.assertIn("'" + value + "'", render_powershell('python', [value]))


if __name__ == '__main__':
    unittest.main()
