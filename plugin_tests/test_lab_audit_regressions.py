"""Independent counterexamples from the local Atmos adoption lab audit.

These assertions were red against 0.2.1, commit 539f942. Native observation is
recorded separately; ordinary test discovery does not invoke an Atmos binary.
"""
import tempfile
import unittest
from pathlib import Path

from intune_iac import runner
from intune_iac.graph import build_graph, query_graph
from intune_iac.io import AppError
from intune_iac.repository import public_resolution, resolve_component


PROJECT = Path(__file__).resolve().parents[1]


class LocalLabAuditRegressions(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'repository'
        self.put('atmos.yaml', '''stacks:
  base_path: stacks
  included_paths: [deploy/**/*]
  name_pattern: "{stage}"
components:
  terraform:
    base_path: components/terraform
    command: /nonexistent/lab-disabled
    auto_generate_backend_file: false
''')
        self.put('stacks/deploy/dev.yaml', '''vars: {stage: dev}
components:
  terraform:
    foundation: {}
    policy: {}
''')

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def resolve(self):
        return resolve_component(self.root, 'deploy/dev', 'policy')

    def proposal(self):
        return runner._proposal('repository_resolve', {
            'root': str(self.root), 'stack': 'deploy/dev', 'component': 'policy',
        }, self.base / 'receipts')[0]

    def test_implementation_presence_is_bound_to_selection_evidence(self):
        before = self.resolve()
        self.assertEqual(before['status'], 'resolved')
        self.assertFalse(before['implementation_exists'])
        implementation = self.root / 'components/terraform/policy'
        implementation.mkdir(parents=True)
        after = self.resolve()
        self.assertTrue(after['implementation_exists'])
        self.assertNotEqual(before['selection_fingerprint'], after['selection_fingerprint'],
                            'A claim used by graph placement changed without invalidating selection evidence.')

    def test_runner_rejects_changed_implementation_presence(self):
        implementation = self.root / 'components/terraform/policy'
        for transition in ('missing_to_directory', 'directory_to_regular_file'):
            with self.subTest(transition=transition):
                proposal = self.proposal()
                if transition == 'missing_to_directory':
                    implementation.mkdir(parents=True)
                else:
                    implementation.rmdir()
                    implementation.write_text('Not a component directory.', encoding='utf-8')
                with self.assertRaises(AppError) as failure:
                    runner._recheck(proposal)
                self.assertEqual(failure.exception.code, 'evidence_changed')

    def test_hcl_bytes_already_invalidate_repository_proposal_control(self):
        proposal = self.proposal()
        self.put('components/terraform/policy/main.tf', '# byte-bound control\n')
        with self.assertRaises(AppError) as failure:
            runner._recheck(proposal)
        self.assertEqual(failure.exception.code, 'evidence_changed')

    def test_graph_action_binds_empty_implementation_directory(self):
        proposal = runner._proposal('graph_build', {
            'input': str(PROJECT / 'examples/supported/input/export.json'),
            'atmos_root': str(self.root), 'output': str(self.base / 'graph.json'),
        }, self.base / 'receipts')[0]
        (self.root / 'components/terraform/policy').mkdir(parents=True)
        with self.assertRaises(AppError) as failure:
            runner._recheck(proposal)
        self.assertEqual(failure.exception.code, 'evidence_changed')

    def test_repository_postcondition_checks_placement_not_only_source_bytes(self):
        proposal = self.proposal()
        result = public_resolution(self.resolve())
        result['implementation_exists'] = True
        with self.assertRaises(AppError) as failure:
            runner._verify('repository_resolve', proposal, result)
        self.assertEqual(failure.exception.code, 'postcondition_failed')

    def test_malformed_dependency_collection_remains_visible_for_selected_component(self):
        # Native Atmos describe dependents rejects the inherited list with
        # "'depends_on' expected type 'schema.DependsOn'". Static analysis may
        # retain it as unknown, but must never silently drop its declaration.
        manifests = {
            'root': '''vars: {stage: dev}
settings: {depends_on: [foundation]}
components:
  terraform:
    foundation: {}
    policy: {}
''',
            'type': '''vars: {stage: dev}
terraform:
  settings: {depends_on: [foundation]}
components:
  terraform:
    foundation: {}
    policy: {}
''',
            'component': '''vars: {stage: dev}
components:
  terraform:
    foundation: {}
    policy:
      settings: {depends_on: [foundation]}
''',
        }
        for scope, manifest in manifests.items():
            with self.subTest(scope=scope):
                self.put('stacks/deploy/dev.yaml', manifest)
                graph = build_graph(PROJECT / 'examples/supported/input/export.json',
                                    atmos_root=self.root)
                selected = next(node for node in graph['nodes']
                                if node['type'] == 'ComponentInstance'
                                and node['name'] == 'policy'
                                and node['resolution_status'] == 'resolved')
                result = query_graph(graph, 'dependencies', selected['id'])
                issues = [issue for issue in result['issues']
                          if 'dependency' in issue['code']]
                self.assertTrue(issues, 'Malformed effective dependency shape disappeared from the selected query.')
                self.assertFalse(result['execution_authorized'])


if __name__ == '__main__':
    unittest.main()
