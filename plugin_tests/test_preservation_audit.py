"""Regression counterexamples from the independent v0.2.0 audit."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from plugin_tests.test_production import inputs
from intune_iac.engine import inspect_source, generate
from intune_iac.production import normalize
from intune_iac.production_oracle import compare

ROOT = Path(__file__).resolve().parents[1]


class PreservationAuditTests(unittest.TestCase):
    def synthetic(self, mutate):
        source = json.loads((ROOT/'examples/supported/input/export.json').read_text())
        context = ROOT/'examples/context.json'
        mutate(source)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'input.json'; output = Path(td)/'project'
            path.write_text(json.dumps(source))
            result = inspect_source(path, context)
            generated = generate(path, context, output)
            self.assertFalse(result['normalized']['offline_mapping_complete'])
            self.assertFalse(list(output.rglob('*.tf')))
            self.assertTrue(generated['preservation_verified'])
            return result

    def test_synthetic_contradictory_count_blocks_active_output(self):
        for kind in range(3):
            with self.subTest(kind=kind):
                self.synthetic(lambda s: s['collections'][kind]['pages'][0]['body'].update({'@odata.count':99}))

    def test_synthetic_malformed_count_blocks_active_output(self):
        for count in [True, '3', -1, None]:
            with self.subTest(count=count):
                self.synthetic(lambda s: s['collections'][2]['pages'][0]['body'].update({'@odata.count':count}))

    def test_synthetic_assignment_flag_disagreement_blocks_active_output(self):
        self.synthetic(lambda s: s['collections'][0]['pages'][0]['body']['value'][0].update(isAssigned=False))

    def test_synthetic_uuid_case_does_not_hide_duplicate_observations(self):
        def assignment_identity(source):
            assignments = source['collections'][2]['pages'][0]['body']['value']
            assignments[1]['id'] = assignments[0]['id'].upper()
        def unselected_policy_identity(source):
            policies = source['collections'][0]['pages'][0]['body']['value']
            other = copy.deepcopy(policies[0])
            other['id'] = 'abcdefab-cdef-4bcd-8abc-abcdefabcdef'
            policies.extend([other, dict(other, id=other['id'].upper())])
        for mutate in [assignment_identity, unselected_policy_identity]:
            with self.subTest(case=mutate.__name__):
                result = self.synthetic(mutate)
                kind = 'assignments' if mutate.__name__ == 'assignment_identity' else 'policies'
                self.assertFalse(next(row for row in result['normalized']['coverage'] if row['kind'] == kind)['complete'])

    def test_synthetic_uuid_case_does_not_hide_duplicate_assignment_targets(self):
        def mutate(source):
            assignments = source['collections'][2]['pages'][0]['body']['value']
            target = copy.deepcopy(assignments[0]['target'])
            target['groupId'] = 'abcdefab-cdef-4bcd-8abc-abcdefabcdef'
            target['deviceAndAppManagementAssignmentFilterId'] = 'fedcbafe-dcba-4cba-8fed-fedcbafedcba'
            assignments[0]['target'] = target
            assignments[1]['target'] = {key: value.upper() if key in {'groupId', 'deviceAndAppManagementAssignmentFilterId'} else value for key, value in target.items()}
            for key, kind in [('groupId','group'), ('deviceAndAppManagementAssignmentFilterId','filter')]:
                reference = copy.deepcopy(next(r for r in source['references'] if r['kind'] == kind))
                reference['id'] = target[key]
                source['references'].append(reference)
        result = self.synthetic(mutate)
        self.assertIn('duplicate_assignment_target', {b['code'] for b in result['blockers']})

    def test_independent_oracle_rejects_promoted_duplicate_uuid_capture(self):
        from reference.core import normalize as normalize_reference
        from reference.invariants import compare as compare_reference
        source = json.loads((ROOT/'examples/supported/input/export.json').read_text())
        context = json.loads((ROOT/'examples/context.json').read_text())
        rows = source['collections'][2]['pages'][0]['body']['value']
        rows[1]['id'] = rows[0]['id'].upper()
        normalized = normalize_reference(source, context['selected_policy_id'], context['tenant_id'])
        self.assertEqual(compare_reference(json.dumps(source).encode(), normalized, context=context), [])
        promoted = copy.deepcopy(normalized)
        promoted.update(offline_mapping_complete=True, blockers=[])
        self.assertIn('mapping_status_changed', compare_reference(json.dumps(source).encode(), promoted, context=context))

    def test_production_assignment_source_must_be_observed(self):
        source, context = inputs()
        for row in source['collections'][2]['pages'][0]['body']['value']:
            row.pop('source')
        result = normalize(source, context)
        self.assertFalse(result['candidate_mapping_complete'])
        self.assertIn('assignment_source_unobserved', {b['code'] for b in result['blockers']})
        self.assertEqual(compare(json.dumps(source).encode(), result, context=context), [])

    def test_node_budget_rejects_before_lineage_or_output_allocation(self):
        from unittest.mock import patch
        from intune_iac.io import AppError
        source, context = inputs()
        source['collections'][1]['pages'][0]['body']['value'][0]['unsupported'] = [0] * 40000
        with patch('intune_iac.production._accounting', side_effect=AssertionError('must not expand ledger')):
            with self.assertRaises(AppError) as error:
                normalize(source, context)
            self.assertEqual(error.exception.code, 'capture_node_limit')
        with patch('intune_iac.production_oracle._derive', side_effect=AssertionError('must not derive')) as derive:
            self.assertTrue(compare(json.dumps(source).encode(), {}, context=context))
            derive.assert_not_called()
        with tempfile.TemporaryDirectory() as td:
            source_path = Path(td)/'source.json'; context_path = Path(td)/'context.json'; output = Path(td)/'project'
            source_path.write_text(json.dumps(source)); context_path.write_text(json.dumps(context))
            with self.assertRaises(AppError) as error:
                generate(source_path, context_path, output)
            self.assertEqual(error.exception.code, 'capture_node_limit')
            self.assertFalse(output.exists())

    def test_large_unselected_inventory_keeps_lineage_bounded(self):
        # A generous subprocess deadline catches a quadratic record search while
        # keeping failures contained; it is not a production latency promise.
        import subprocess
        import sys
        code = """
import json
from uuid import UUID
from plugin_tests.test_production import inputs
from intune_iac.production import normalize
from intune_iac.production_oracle import compare
source, context = inputs()
source['collections'][0]['pages'][0]['body']['value'].extend(
    {'id': str(UUID(int=i + 1))} for i in range(4000))
normalized = normalize(source, context)
assert normalized['candidate_mapping_complete'] is True
assert compare(json.dumps(source).encode(), normalized, context=context) == []
print('complete')
"""
        runtime_root = Path(sys.modules['intune_iac.engine'].__file__).resolve().parents[1]
        completed = subprocess.run([sys.executable, '-c', code], cwd=runtime_root,
                                   capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), 'complete')

    def test_production_lineage_schema_and_destinations_hold_when_blocked(self):
        from jsonschema import Draft202012Validator
        schema = json.loads((ROOT/'contracts/production-field-accounting.schema.json').read_text())
        for mutation in ['none', 'opaque_id', 'unsupported_policy', 'unsupported_body', 'denied', 'empty_assignments']:
            with self.subTest(mutation=mutation):
                source, context = inputs()
                if mutation == 'opaque_id':
                    source['collections'][1]['pages'][0]['body']['value'][0]['id'] = 'opaque-id'
                elif mutation == 'unsupported_policy':
                    source['collections'][0]['pages'][0]['body']['value'][0]['private-unrecognized'] = 3
                elif mutation == 'unsupported_body':
                    source['collections'][1]['pages'][0]['body']['private-unrecognized'] = 3
                elif mutation == 'denied':
                    source['collections'][2]['pages'][0].update(http_status=403, body={'error':{'message':'private-unrecognized'}})
                elif mutation == 'empty_assignments':
                    source['collections'][2]['pages'][0]['body']['value'] = []
                    source['collections'][0]['pages'][0]['body']['value'][0]['isAssigned'] = False
                result = normalize(source, context)
                self.assertEqual(list(Draft202012Validator(schema).iter_errors(result['field_accounting'])), [])
                for row in result['field_accounting']:
                    for destination in row['destination_pointers']:
                        current = result
                        for token in destination.split('/')[1:]:
                            current = current[int(token)] if isinstance(current, list) else current[token.replace('~1','/').replace('~0','~')]
                self.assertEqual(compare(json.dumps(source).encode(), result, context=context), [])

    def test_production_lineage_accounts_for_destinations_and_retention(self):
        source, context = inputs()
        result = normalize(source, context)
        pointer = '/collections/1/pages/0/body/value/0/settingInstance/choiceSettingValue/value'
        row = next(r for r in result['field_accounting'] if r['source_node_ref'] == hashlib.sha256(pointer.encode()).hexdigest())
        self.assertEqual(row.get('disposition'), 'desired')
        self.assertIn('/configuration/settings/settings/0/settingInstance/choiceSettingValue/value', row['destination_pointers'])
        self.assertEqual(row['rule_version'], '1.1.0')
        self.assertFalse(row['loss_blocking'])
        for field, bad in [('disposition', 'service_owned'), ('destination_pointers', []), ('rule_id', 'made_up'), ('loss_blocking', True)]:
            changed = copy.deepcopy(result)
            changed_row = next(r for r in changed['field_accounting'] if r['source_node_ref'] == row['source_node_ref'])
            changed_row[field] = bad
            self.assertTrue(compare(json.dumps(source).encode(), changed, context=context))
        source['collections'][1]['pages'][0]['body']['value'][0]['SECRET-NAME'] = 'SECRET-VALUE'
        blocked = normalize(source, context)
        self.assertFalse(blocked['candidate_mapping_complete'])
        self.assertNotIn('SECRET-', json.dumps(blocked))
        self.assertTrue(any(r['disposition'] == 'unsupported' and r['loss_blocking'] for r in blocked['field_accounting']))
        self.assertEqual(compare(json.dumps(source).encode(), blocked, context=context), [])


if __name__ == '__main__': unittest.main()
