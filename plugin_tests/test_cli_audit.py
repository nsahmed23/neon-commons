import unittest
from intune_iac.cli import exit_code


class CliAuditTests(unittest.TestCase):
    def test_missing_dependencies_uses_documented_exit_five(self):
        self.assertEqual(exit_code({'status': 'missing_dependencies'}), 5)

    def test_nested_missing_dependencies_uses_exit_five(self):
        self.assertEqual(exit_code({'status': 'succeeded_verified',
                                    'result': {'status': 'missing_dependencies'}}), 5)


if __name__ == '__main__':
    unittest.main()
