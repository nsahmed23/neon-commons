"""Every authorization family's expiry table is registered in validity.FAMILIES (PKG-AUTHZ-D fix round 2).

The database-level migration cutoff treats a row in a registered family's table (its base, version 2 or open table, whatever
its columns) as authorization history, and nothing outside the registry. A family added without being registered would have
its legacy rows ignored, so this guard fails when the code constructs a validity.Store with a table the registry does not
list.
"""
import ast
import unittest
from pathlib import Path

from intune_iac import validity

PACKAGE = Path(__file__).resolve().parent.parent / 'intune_iac'


def _strings(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


class RegistryGuardTests(unittest.TestCase):
    def modules(self):
        for path in sorted(PACKAGE.glob('*.py')):
            yield path, ast.parse(path.read_text(encoding='utf-8'))

    def test_every_store_constructed_in_the_package_names_a_registered_family(self):
        seen = []
        for path, tree in self.modules():
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'Store'
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == 'validity'):
                    table = node.args[2] if len(node.args) > 2 else None
                    literal = _strings(table)
                    seen.append((path.name, node.lineno, literal))
                    if literal is not None:
                        self.assertIn(literal, validity.FAMILIES, '%s:%d builds a Store for an unregistered family' % (path.name, node.lineno))
        self.assertTrue(seen, 'the scan found no Store construction: the guard is broken')

    def test_every_table_constant_in_the_package_is_registered(self):
        # A Store built from a variable (the service store takes its table as a parameter) is covered through the module-level
        # *_TABLE constants that name the tables its callers pass.
        found = []
        for path, tree in self.modules():
            for node in tree.body:
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    if node.targets[0].id.endswith('_EXPIRED_TABLE') or node.targets[0].id == 'EXPIRED_TABLE':
                        literal = _strings(node.value)
                        found.append((path.name, node.targets[0].id))
                        self.assertIn(literal, validity.FAMILIES, '%s defines %s outside the registry' % (path.name, node.targets[0].id))
        self.assertGreaterEqual(len(found), 4)

    def test_the_registry_holds_valid_distinct_family_names(self):
        self.assertEqual(len(set(validity.FAMILIES)), len(validity.FAMILIES))
        for name in validity.FAMILIES:
            validity.table_sql(name)  # raises for a name that is not a valid base table


if __name__ == '__main__':
    unittest.main()
