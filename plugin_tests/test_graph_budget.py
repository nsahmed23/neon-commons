"""Reject expensive complete inventories before repeated per-policy projection."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from intune_iac.graph import build_graph, query_graph
from intune_iac.io import AppError

ROOT = Path(__file__).resolve().parents[1]


class GraphBudgetTests(unittest.TestCase):
    def test_stored_graph_query_budget_precedes_digest_and_relational_scans(self):
        graph = {'schema_version': 'intune-review-graph/1.0', 'nodes': [{}] * 2000,
                 'edges': [{}] * 1001, 'sources': [], 'coverage': [], 'issues': [],
                 'execution_authorized': False, 'live_qualification': 'not_run',
                 'atmos': {'resolution_status': 'not_requested'}, 'graph_digest': '0' * 64}
        with patch('intune_iac.graph_validation.digest') as digest:
            with self.assertRaisesRegex(AppError, 'work budget'):
                query_graph(graph, 'policies')
            digest.assert_not_called()

    def test_many_policy_projection_is_rejected_before_normalization(self):
        source = json.loads((ROOT / 'examples/supported/input/export.json').read_text())
        rows = source['collections'][0]['pages'][0]['body']['value']
        original = rows[0]
        rows[:] = [dict(copy.deepcopy(original), id=str(UUID(int=i + 1))) for i in range(65)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.json'
            path.write_text(json.dumps(source))
            before = path.read_bytes()
            with patch('intune_iac.graph.normalize', side_effect=ValueError('unsupported fixture')) as normalize:
                with self.assertRaisesRegex(AppError, 'complete capture intact'):
                    build_graph(path)
                normalize.assert_not_called()
            self.assertEqual(path.read_bytes(), before)

    def test_large_unselected_payload_counts_toward_projection_work(self):
        source = json.loads((ROOT / 'examples/supported/input/export.json').read_text())
        source['unselected'] = [0] * 10001
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.json'
            path.write_text(json.dumps(source))
            with patch('intune_iac.graph.normalize', side_effect=ValueError('unsupported fixture')) as normalize:
                with self.assertRaisesRegex(AppError, 'complete capture intact'):
                    build_graph(path)
                normalize.assert_not_called()

    def test_small_node_count_cannot_hide_large_repeated_byte_work(self):
        source = json.loads((ROOT / 'examples/supported/input/export.json').read_text())
        source['unselected'] = 'x' * (5 * 1024 * 1024)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.json'
            path.write_text(json.dumps(source))
            with patch('intune_iac.graph.normalize', side_effect=ValueError('unsupported fixture')) as normalize:
                with self.assertRaisesRegex(AppError, 'complete capture intact'):
                    build_graph(path)
                normalize.assert_not_called()
