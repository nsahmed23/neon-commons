"""The actual wizard-to-workbench handoff preserves its completed evidence."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from intune_iac.io import AppError, load_json, write_json
from intune_iac.synthetic import generate_estate
from intune_iac.workbench_store import WorkbenchStore

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/intune-iac.py'


class WorkbenchAdoptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.estate = generate_estate(seed=721, policy_count=2)
        self.ids = [row['id'] for row in self.estate['truth']['policies']]
        self.tenant = self.estate['truth']['tenant_id']
        self.capture = self.root / 'capture.json'
        self.context = self.root / 'context.json'
        self.session = self.root / 'adoption session.json'
        self.output = self.root / 'generated proposal'
        self.store_root = self.root / 'observations'
        self.handoff = self.root / 'maintenance handoff'
        write_json(self.capture, self.estate['capture'])
        write_json(self.context, self.estate['contexts'][0])
        self.store = WorkbenchStore.create(self.store_root, self.tenant)

    def process(self, *args, input=None):
        return subprocess.run([sys.executable, '-B', str(CLI), *map(str, args)], input=input,
                              text=True, capture_output=True, cwd='/tmp', timeout=40,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))

    def call(self, *args):
        result = self.process('workbench', *args)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def complete(self, repo=None):
        answers = ['continue'] * 3 + [','.join(self.ids)] + ['continue'] * 4
        answers += ['generate', 'continue', 'continue', 'plan', 'approve', 'execute', 'reconcile', 'continue', 'finish']
        args = ['wizard', '--journey', '--session', self.session, '--input', self.capture,
                '--context', self.context, '--output', self.output]
        if repo is not None: args += ['--repo', repo]
        result = self.process(*args, input='\n'.join(answers) + '\n')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(load_json(self.session)['lifecycle'], 'complete_simulation', result.stdout)

    def adopt(self):
        return self.call('adopt', '--root', self.store_root, '--session', self.session, '--output', self.handoff)

    def test_actual_cli_connects_completed_adoption_to_persistent_inspection(self):
        self.complete()
        original_service = Path(str(self.session) + '.journey') / 'modeled-service/service.json'
        original = original_service.read_bytes()
        result = self.adopt()
        self.assertEqual(result['status'], 'adopted_local_model')
        self.assertEqual(result['evidence_class'], 'synthetic')  # the collection run's own class
        self.assertEqual(result['object_ids'], sorted(self.ids))
        self.assertEqual(result['service_root'], str(self.handoff / 'service'))
        self.assertEqual(original_service.read_bytes(), original)
        for oid in self.ids:
            seen = self.call('inspect', '--root', self.store_root, '--object', oid)
            self.assertEqual(seen['object_id'], oid)
            self.assertIn('exclusionGroupAssignmentTarget', [x['type'] for x in seen['body']['assignments']])
            lineage = self.call('adoption-lineage', '--root', self.store_root, '--object', oid)
            self.assertEqual(len(lineage['adoptions']), 1)
            binding = lineage['adoptions'][0]['data']['binding']
            self.assertEqual(binding['object_ids'], sorted(self.ids))
            self.assertFalse(binding['native_provider_execution'])
            self.assertFalse(binding['cloud_execution'])

    def test_preview_is_read_only_and_rejects_wrong_tenant(self):
        self.complete()
        def files(): return {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        before = files()
        result = self.call('adoption-preview', '--root', self.store_root, '--session', self.session)
        self.assertEqual(result['status'], 'ready_local_model_handoff')
        self.assertEqual(files(), before)
        wrong = self.root / 'other tenant'
        WorkbenchStore.create(wrong, '99999999-9999-4999-8999-999999999999')
        rejected = self.process('workbench', 'adopt', '--root', wrong, '--session', self.session, '--output', self.handoff)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('workbench_adoption_wrong_tenant', rejected.stderr)
        self.assertFalse(self.handoff.exists())

    def test_completion_flags_receipts_source_and_generated_tampering_rejected(self):
        self.complete()
        receipt = Path(str(self.session) + '.journey/receipts/adoption.json')
        generated = self.output / self.ids[0] / 'README.md'
        scenarios = [(self.session, lambda d: d.update(in_flight='execute')),
                     (self.session, lambda d: d.update(mode='live')),
                     (self.session, lambda d: d.update(selected_ids=['99999999-9999-4999-8999-999999999999'])),
                     (receipt, lambda d: d['payload'].update(live_import_allowed=True)),
                     (self.capture, lambda d: d.update(tenant_id='99999999-9999-4999-8999-999999999999'))]
        for path, mutate in scenarios:
            with self.subTest(path=path, mutate=mutate):
                original = path.read_bytes()
                value = load_json(path); mutate(value); write_json(path, value)
                result = self.process('workbench', 'adopt', '--root', self.store_root, '--session', self.session, '--output', self.handoff)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.handoff.exists())
                path.write_bytes(original)
        generated.write_text('Changed generated bytes')
        result = self.process('workbench', 'adopt', '--root', self.store_root, '--session', self.session, '--output', self.handoff)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.handoff.exists())

    def test_missing_receipt_and_hardlinked_session_rejected(self):
        self.complete()
        receipt = Path(str(self.session) + '.journey/receipts/handoff.json')
        original = receipt.read_bytes(); receipt.unlink()
        result = self.process('workbench', 'adoption-preview', '--root', self.store_root, '--session', self.session)
        self.assertNotEqual(result.returncode, 0)
        receipt.write_bytes(original)
        os.link(self.session, self.root / 'linked-session')
        result = self.process('workbench', 'adoption-preview', '--root', self.store_root, '--session', self.session)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unsafe_file_identity', result.stderr)

    def test_partial_artifact_publication_resumes_without_model_recreation(self):
        from intune_iac.workbench_adoption import adopt
        self.complete()
        original_record = self.store.record_artifact
        calls = []
        def fail_second(*args, **kwargs):
            calls.append(args)
            if len(calls) == 2: raise AppError('injected_publication_failure', 'Local write failed.')
            return original_record(*args, **kwargs)
        with patch.object(self.store, 'record_artifact', side_effect=fail_second):
            with self.assertRaisesRegex(AppError, 'Local write failed'):
                adopt(self.store, self.session, self.handoff)
        state = load_json(self.handoff / 'adoption.json')
        self.assertEqual(state['status'], 'collected')
        self.assertEqual(len(state['artifact_ids']), 1)
        service_file = self.handoff / 'service/service.json'
        result = self.adopt()
        self.assertEqual(len(result['adoptions']), 2)
        self.assertEqual(len(self.store.artifacts(kind='adoption')), 2)
        self.assertTrue(all(not row['mutation_committed'] for row in load_json(service_file)['requests']))
        # Atomic request publication may replace the inode, but initialization
        # and its exact initial estate must never be repeated or reset.
        self.assertEqual(load_json(service_file)['revision'], 1)
        count = len(load_json(service_file)['requests'])
        repeated = self.adopt()
        self.assertEqual(repeated, result)
        self.assertEqual(len(load_json(service_file)['requests']), count)

    def test_partial_creation_is_retained_and_changed_model_cannot_resume(self):
        from intune_iac.workbench_adoption import adopt
        from intune_iac.modeled_service import BASE, ModeledService
        self.complete()
        with patch.object(self.store, 'record_artifact', side_effect=OSError('injected disk failure')):
            with self.assertRaises(OSError): adopt(self.store, self.session, self.handoff)
        service = ModeledService(self.handoff / 'service')
        before = service.snapshot()
        desired = copy.deepcopy(before['current']['objects'][self.ids[0]])
        desired['description'] = 'A later intentional change prevents adoption replay'
        service.request('PATCH', BASE + '/' + self.ids[0], tenant_id=self.tenant, body=desired, if_match='1')
        result = self.process('workbench', 'adopt', '--root', self.store_root, '--session', self.session, '--output', self.handoff)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('workbench_adoption_partial_model_changed', result.stderr)
        self.assertEqual(service.snapshot()['current']['objects'][self.ids[0]]['description'], desired['description'])

    def test_lineage_survives_later_collection_and_terminal_reopen(self):
        self.complete()
        initial = self.process('workbench', 'terminal', '--root', self.store_root,
                               input=f'adopt {json.dumps(str(self.session))} {json.dumps(str(self.handoff))}\nselect {self.ids[0]}\ncollect\nquit\n')
        self.assertEqual(initial.returncode, 0, initial.stderr)
        self.assertIn('adopted_local_model', initial.stdout)
        self.assertNotIn('service_required', initial.stdout)
        self.assertEqual(len(self.store.collection_history()), 2)
        lineage = self.call('adoption-lineage', '--root', self.store_root, '--object', self.ids[0])
        self.assertEqual(len(lineage['adoptions']), 1)
        terminal = self.process('workbench', 'terminal', '--root', self.store_root,
                                input=f'select {self.ids[0]}\nadoption-lineage\nrelationships\nback\nadoption-lineage\nquit\n')
        self.assertEqual(terminal.returncode, 0, terminal.stderr)
        self.assertIn('historical_local_adoption', terminal.stdout)
        self.assertIn('selection_required', terminal.stdout)
        self.assertIn('generated_from', terminal.stdout)

    def test_existing_repository_source_and_literal_inheritance_are_bound(self):
        repo = self.root / 'existing repository'
        (repo / 'stacks').mkdir(parents=True)
        (repo / 'components/terraform/intune-reference').mkdir(parents=True)
        (repo / 'atmos.yaml').write_text('stacks:\n  base_path: stacks\n  included_paths: ["reference-dev"]\ncomponents:\n  terraform:\n    base_path: components/terraform\n    command: tofu\n')
        (repo / 'stacks/defaults.yaml').write_text('vars:\n  region: inherited\n')
        (repo / 'stacks/reference-dev.yaml').write_text('import: [defaults]\ncomponents:\n  terraform:\n    intune-reference:\n      vars:\n        approved: false\n')
        self.complete(repo)
        result = self.adopt()
        binding = result['adoptions'][0]['data']['binding']
        self.assertEqual(binding['repository']['status'], 'resolved')
        self.assertIn('/vars/region', binding['repository']['provenance'])
        self.assertFalse(binding['native_atmos_configuration_only'])
        self.assertNotIn('effective', binding['repository'])

    def test_output_overlap_and_foreign_existing_directory_are_preserved(self):
        self.complete()
        for target in (self.store_root, self.output, Path(str(self.session) + '.journey'),
                       self.store_root / '..' / self.store_root.name / 'inside'):
            result = self.process('workbench', 'adopt', '--root', self.store_root, '--session', self.session, '--output', target)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('workbench_adoption_path_overlap', result.stderr)
        alias = self.store_root / '..' / self.store_root.name
        result = self.process('workbench', 'adopt', '--root', alias, '--session', self.session,
                              '--output', self.store_root / 'inside')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('workbench_adoption_path_overlap', result.stderr)
        self.assertFalse((self.store_root / 'inside').exists())
        self.handoff.mkdir(mode=0o700)
        marker = self.handoff / 'user-file'; marker.write_text('keep')
        result = self.process('workbench', 'adopt', '--root', self.store_root, '--session', self.session, '--output', self.handoff)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(marker.read_text(), 'keep')

    def test_complete_checkpoint_requires_exact_artifacts_and_persisted_observation(self):
        self.complete(); self.adopt()
        checkpoint = self.handoff / 'adoption.json'
        original = load_json(checkpoint)
        mutations = [lambda d: d.update(artifact_ids={}),
                     lambda d: d.update(collection_run_id=999999),
                     lambda d: d['artifact_ids'].update({self.ids[0]: d['artifact_ids'][self.ids[1]]})]
        for mutate in mutations:
            changed = copy.deepcopy(original); mutate(changed); write_json(checkpoint, changed)
            result = self.process('workbench', 'adopt', '--root', self.store_root, '--session', self.session, '--output', self.handoff)
            self.assertNotEqual(result.returncode, 0, result.stdout)
        write_json(checkpoint, original)
        with self.store._connection(True) as db, db:
            row = db.execute('SELECT snapshot_id, body_json FROM snapshots WHERE object_id=?', (self.ids[0],)).fetchone()
            body = json.loads(row['body_json']); body['assignments'] = []
            db.execute('UPDATE snapshots SET body_json=? WHERE snapshot_id=?', (json.dumps(body), row['snapshot_id']))
        result = self.process('workbench', 'adopt', '--root', self.store_root, '--session', self.session, '--output', self.handoff)
        self.assertNotEqual(result.returncode, 0, result.stdout)


class AdoptionSummaryTests(unittest.TestCase):
    """In the workspace the preview and the adopt result say what they found and did (journey 25 showed both empty)."""
    setUp = WorkbenchAdoptionTests.setUp
    process = WorkbenchAdoptionTests.process
    call = WorkbenchAdoptionTests.call
    complete = WorkbenchAdoptionTests.complete

    def summary(self, value):
        from plugin_tests.test_workbench_states import RefusalCauseTests
        workspace = RefusalCauseTests.workspace(self)
        workspace.tab, workspace.value, workspace.selected = 0, value, None
        return ' '.join(' '.join(workspace._summary_lines(118)).split())

    def test_the_preview_says_what_adopt_would_create_and_that_nothing_is_sent(self):
        from intune_iac.workbench_adoption import preview
        self.complete()
        text = self.summary(preview(self.store, self.session))
        self.assertIn('[ADOPTION PREVIEW] Ready to hand off 2 policies into a separate local maintenance model', text)
        for object_id in self.ids:
            self.assertIn(object_id, text)
        self.assertIn(str(self.session), text)
        self.assertIn('kept unchanged', text)
        self.assertIn('Repository: none supplied (local context only)', text)
        self.assertIn('Ownership: unknown', text)
        self.assertIn('What adopt does:', text)
        self.assertIn('sends nothing to a tenant', text)
        self.assertIn('Next: adopt', text)

    def test_the_adopt_result_names_the_handoff_and_how_to_use_it(self):
        from intune_iac.workbench_adoption import adopt
        self.complete()
        result = adopt(self.store, self.session, self.handoff)
        text = self.summary(result)
        self.assertIn('[ADOPTED] 2 policies handed off to a local maintenance model', text)
        self.assertIn('Handoff: ' + str(self.handoff), text)
        self.assertIn('Modeled service: ' + str(self.handoff / 'service'), text)
        self.assertIn('Collection run %s recorded in this store' % result['collection_run_id'], text)
        self.assertIn('Original journey kept', text)
        # Since a405bf1 a reopened store uses the adopted service; the next step no longer asks for it.
        self.assertIn('without --service-root', text)

    def test_one_adopted_policy_is_named_in_the_singular(self):
        from intune_iac.workbench_screens import adoption_lines
        text = ' '.join(' '.join(adoption_lines({'status': 'adopted_local_model', 'object_ids': ['x'], 'adoptions': [],
                                                 'service_root': '/s', 'original_journey_preserved': True}, 118)).split())
        self.assertIn('1 policy handed off', text)
        self.assertIn('lists the adopted policy.', text)


if __name__ == '__main__':
    unittest.main()


class AdoptedServiceTests(unittest.TestCase):
    """After adopt, reopening the store needs no --service-root: the latest adoption record names the modeled service
    (owner directive inbox/PRODUCT-TASK-12.md, section 4)."""
    setUp = WorkbenchAdoptionTests.setUp
    process = WorkbenchAdoptionTests.process
    call = WorkbenchAdoptionTests.call
    complete = WorkbenchAdoptionTests.complete
    adopt = WorkbenchAdoptionTests.adopt

    def terminal(self, commands, **kwargs):
        from intune_iac.workbench import run_terminal
        lines, pending = [], iter(commands)

        def read(prompt):
            try:
                return next(pending)
            except StopIteration:
                raise EOFError
        run_terminal(self.store_root, input_fn=read, output_fn=lines.append, **kwargs)
        documents, decoder, text, index = [], json.JSONDecoder(), '\n'.join(lines), 0
        while index < len(text):
            if text[index] == '{':
                value, index = decoder.raw_decode(text, index)
                documents.append(value)
            else:
                index += 1
        return documents

    @staticmethod
    def origins(documents):
        return [document['modeled_service'] for document in documents if 'modeled_service' in document]

    def test_a_reopened_store_uses_the_adopted_service_without_a_flag(self):
        self.complete()
        adopted = self.adopt()
        latest = self.store.latest_artifact('adoption')
        self.assertEqual(latest['data']['maintenance_service_root'], str(self.handoff / 'service'))
        self.assertIn(latest['artifact_id'], [row['artifact_id'] for row in adopted['adoptions']])
        before = len(self.store.collection_history())
        documents = self.terminal(['overview', 'collect'])
        self.assertEqual(self.origins(documents)[0], {'root': str(self.handoff / 'service'), 'source': 'adoption',
                                                      'artifact_id': latest['artifact_id']})
        self.assertFalse(any((document.get('error') or {}).get('code') == 'service_required' for document in documents))
        self.assertEqual(len(self.store.collection_history()), before + 1)

    def test_an_explicit_service_root_wins_and_says_so(self):
        self.complete()
        self.adopt()
        other = self.root / 'other service'
        from intune_iac.modeled_service import ModeledService
        ModeledService.create(other, self.estate['capture'], self.ids)
        documents = self.terminal(['overview'], service_root=other)
        self.assertEqual(self.origins(documents)[0], {'root': str(other), 'source': 'command line'})

    def test_without_an_adoption_the_store_names_no_service(self):
        self.assertIsNone(self.store.latest_artifact('adoption'))
        self.assertEqual(self.origins(self.terminal(['overview']))[0], None)

    def test_a_missing_adopted_service_is_reported_not_used(self):
        import shutil
        self.complete()
        self.adopt()
        shutil.rmtree(self.handoff / 'service')
        documents = self.terminal(['overview', 'collect'])
        self.assertEqual(self.origins(documents)[0]['problem'], 'service_unavailable')
        self.assertTrue(any((document.get('error') or {}).get('code') == 'service_required' for document in documents))

    def test_the_estate_surface_says_which_service_and_why(self):
        from intune_iac.workbench_screens import service_words
        self.assertEqual(service_words({'root': '/work/handoff/service', 'source': 'adoption', 'artifact_id': 'a' * 64}),
                         'Modeled service: /work/handoff/service (from the latest adoption record aaaaaaaaaaaa; '
                         '--service-root chooses another)')
        self.assertEqual(service_words({'root': '/work/service', 'source': 'command line'}),
                         'Modeled service: /work/service (--service-root)')
        self.assertEqual(service_words(None),
                         'Modeled service: none yet. Adopt a completed journey (:adopt), or start with --service-root.')
        self.assertEqual(service_words({'root': '/gone', 'source': 'adoption', 'artifact_id': 'b' * 64,
                                        'problem': 'service_unavailable'}),
                         'Modeled service: unavailable. The latest adoption record bbbbbbbbbbbb names /gone, which '
                         'cannot be opened for this tenant; start with --service-root.')
