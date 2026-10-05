"""Adversarial input regressions with independent controls; no external calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from intune_iac.graph import build_graph, query_graph
from intune_iac.io import AppError, digest, parse_json
from reference.core import normalize
from reference.invariants import compare

ROOT = Path(__file__).resolve().parents[1]


class EdgeInputAuditTests(unittest.TestCase):
    def graph(self):
        return build_graph(ROOT / 'examples/supported/input/export.json')

    def reject_graph(self, graph):
        # Rehash so validation must inspect semantics, not just a stale checksum.
        graph['graph_digest'] = digest({k: v for k, v in graph.items() if k != 'graph_digest'})
        with self.assertRaises(AppError) as error:
            query_graph(graph, 'policies')
        self.assertEqual(error.exception.code, 'invalid_graph')

    def test_distinct_edges_cannot_share_identity(self):
        graph = self.graph()
        graph['edges'][1]['id'] = graph['edges'][0]['id']
        self.reject_graph(graph)

    def test_coverage_claim_identity_is_unique_even_if_status_agrees(self):
        for status in ('complete', 'unknown'):
            with self.subTest(status=status):
                graph = self.graph()
                duplicate = copy.deepcopy(graph['coverage'][0])
                duplicate['status'] = status
                graph['coverage'].append(duplicate)
                self.reject_graph(graph)

    def test_coverage_subject_type_matches_aspect(self):
        graph = self.graph()
        graph['coverage'][0]['subject_id'] = next(n['id'] for n in graph['nodes'] if n['type'] == 'Assignment')
        self.reject_graph(graph)

    def test_required_capture_coverage_cannot_disappear(self):
        graph = self.graph()
        graph['coverage'] = []
        self.reject_graph(graph)

    def test_valid_complete_and_denied_graphs_preserve_unknown(self):
        for fixture, expected in (('supported', 'complete'), ('access-denied', 'unknown')):
            with self.subTest(fixture=fixture):
                graph = build_graph(ROOT / 'examples' / fixture / 'input/export.json')
                result = query_graph(graph, 'assignments', '22222222-2222-4222-8222-222222222222')
                self.assertEqual(result['coverage'][0]['status'], expected)
                self.assertFalse(result['execution_authorized'])

    def test_declared_atmos_coverage_remains_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'dev.yaml').write_text('components:\n  terraform:\n    policy: {}\n')
            graph = build_graph(ROOT / 'examples/supported/input/export.json', atmos_root=root)
            query_graph(graph, 'dependencies')
            declarations = {n['id'] for n in graph['nodes'] if n['type'] == 'StackDeclaration'}
            row = next(c for c in graph['coverage'] if c['subject_id'] in declarations)
            self.assertEqual(row['status'], 'unknown')
            row['status'] = 'complete'
            self.reject_graph(graph)

    def test_synthetic_oracle_distinguishes_boolean_and_integer(self):
        source = json.loads((ROOT / 'examples/supported/input/export.json').read_text())
        context = json.loads((ROOT / 'examples/context.json').read_text())
        baseline = normalize(source, context['selected_policy_id'], context['tenant_id'])
        raw = json.dumps(source).encode()
        self.assertEqual(compare(raw, baseline, context=context), [])
        for case in ('observed_count', 'mapping_flag', 'coverage_flag'):
            with self.subTest(case=case):
                changed = copy.deepcopy(baseline)
                if case == 'observed_count':
                    changed['observed']['policy']['settingCount'] = True
                elif case == 'mapping_flag':
                    changed['offline_mapping_complete'] = 1
                else:
                    changed['coverage'][0]['complete'] = 1
                self.assertTrue(compare(raw, changed, context=context))

    def test_json_boundaries_fail_closed_without_raw_diagnostics(self):
        for payload in ('{"x":1,"\\u0078":2}', '{"CANARY":1e999}',
                        '{"CANARY":9007199254740992}', '{"CANARY":"\\ud800"}',
                        '[' * 65 + '0' + ']' * 65):
            with self.subTest(payload=payload[:24]):
                with self.assertRaises(AppError) as error:
                    parse_json(payload)
                self.assertEqual(error.exception.code, 'invalid_json')
                self.assertNotIn('CANARY', error.exception.message)
        self.assertEqual(parse_json('[' * 64 + '0' + ']' * 64), json.loads('[' * 64 + '0' + ']' * 64))
        self.assertEqual(parse_json('9007199254740991'), 9007199254740991)


if __name__ == '__main__':
    unittest.main()
