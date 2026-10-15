"""P3c round 2: the execution side of the pin migration, and the review fixes.

Round 1 made generation choose its pins by the context schema version. This module covers what Fable's review found
was still on the legacy pair: the capture route (a captured context is 2.0.0, a stored 1.0.0 one is labelled), the
journey (it shows which pins it generated, or says it is reproducing legacy ones), plan review, the modeled
executor, the workflow store, and the labels and defaults listed in the review.

Every expectation about the pins is read from native_pins.py through plugin_tests.test_pin_migration_p3c; nothing here
touches the P3a frozen fixtures or the P3b history modules.
"""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from plugin_tests import test_pin_migration_p3c as p3c
from plugin_tests.test_pin_migration_p3c import (CONTEXT_V1, CONTEXT_V2, CURRENT, CURRENT_ATMOS, CURRENT_TOFU, LEGACY,
                                                 LEGACY_ATMOS, LEGACY_TOFU, with_pins)

ROOT = Path(__file__).resolve().parents[1]
T = '11111111-1111-4111-8111-111111111111'
P = '22222222-2222-4222-8222-222222222222'
LEGACY_NOTICE_WORDS = 'reproduce earlier output only'


def example_context():
    return json.loads((ROOT / 'examples/context.json').read_text())


# ---------------------------------------------------------------------------------------------------------------------
# Item 1a: the capture route.
# ---------------------------------------------------------------------------------------------------------------------
class CaptureRouteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'capture'
        fixture = json.loads((ROOT / 'examples/supported/input/export.json').read_text())
        self.responses = {p['request_url']: (p['http_status'], json.dumps(p['body']).encode())
                          for c in fixture['collections'] for p in c['pages']}
        for url, (status, raw) in list(self.responses.items()):
            if url.endswith('/assignments'):
                body = json.loads(raw)
                for row in body['value']:
                    row.update(source='direct', sourceId=None)
                self.responses[url] = (status, json.dumps(body).encode())

    def make(self):
        from intune_iac.capture import capture
        capture(T, P, self.path, transport=lambda url: self.responses[url])

    def load(self):
        from intune_iac.capture_adapter import load_capture
        return load_capture(self.path, tenant_id=T)

    def rewrite_context(self, context):
        path = self.path / 'context.json'
        path.write_text(json.dumps(context))
        receipt = json.loads((self.path / 'capture-receipt.json').read_text())
        receipt['context_byte_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        (self.path / 'capture-receipt.json').write_text(json.dumps(receipt))

    def test_a_captured_context_is_version_2_and_selects_the_current_pins(self):
        from intune_iac.pin_profiles import context_pin_report
        self.make()
        context = json.loads((self.path / 'context.json').read_text())
        self.assertEqual(context['schema_version'], CONTEXT_V2)
        for key in ('engine_version', 'atmos_version', 'provider_version'):
            self.assertNotIn(key, context)  # the toolchain is not observed: the version selects the pins
        self.assertEqual(context_pin_report(context)['pin_profile'], CURRENT)

    def test_a_captured_context_generates_the_current_pins(self):
        from intune_iac.engine import generate
        self.make()
        result = generate(self.path / 'export.json', self.path / 'context.json', self.root / 'project')
        self.assertEqual(result['pin_profile'], CURRENT)

    def test_the_adapter_accepts_both_versions_and_labels_the_legacy_one(self):
        self.make()
        current = self.load()
        self.assertEqual(current['source']['pin_profile'], CURRENT)
        self.assertNotIn('pin_notice', current['source'])
        self.rewrite_context(dict(json.loads((self.path / 'context.json').read_text()), schema_version=CONTEXT_V1))
        legacy = self.load()
        self.assertEqual(legacy['source']['pin_profile'], LEGACY)
        self.assertIn(LEGACY_NOTICE_WORDS, legacy['source']['pin_notice'])
        self.assertEqual(legacy['capture_sha256'] == current['capture_sha256'], False)  # the context bytes differ

    def test_the_adapter_still_refuses_an_unknown_context_version(self):
        from intune_iac.io import AppError
        self.make()
        for version in ('3.0.0', '1.0', None):
            with self.subTest(version=version):
                context = json.loads((self.path / 'context.json').read_text())
                context['schema_version'] = version
                self.rewrite_context(context)
                with self.assertRaises(AppError):
                    self.load()



# ---------------------------------------------------------------------------------------------------------------------
# Item 1b: the journey shows the pins it generated, or says it reproduces legacy ones.
# ---------------------------------------------------------------------------------------------------------------------
class JourneyPinsTests(unittest.TestCase):
    from plugin_tests import test_journey_completion as _base
    setUp = _base.JourneyCompletionTests.setUp
    api = _base.JourneyCompletionTests.api
    run_flow = _base.JourneyCompletionTests.run_flow
    complete = _base.JourneyCompletionTests.complete
    BEFORE = _base.BEFORE_GENERATE
    POLICY = _base.POLICY

    def use(self, profile):
        self.context.write_text(json.dumps(with_pins(example_context(), profile)))

    def generated(self, profile):
        self.use(profile)
        self.run_flow(self.BEFORE + ['generate', 'save'])
        return self.api().reconstruct_progress(self.session)

    def receipt(self, stage):
        return json.loads((self.session.parent / (self.session.name + '.journey') / 'receipts' / (stage + '.json')).read_text())

    def work(self, name):
        return self.session.parent / (self.session.name + '.journey') / 'synthetic-executor/work' / name

    def test_a_v2_context_generates_the_current_pins_and_the_journey_shows_them(self):
        progress = self.generated(CURRENT)
        self.assertIn('generation', progress['verified_completed'])
        self.assertEqual(progress['pin_profile'], CURRENT)
        self.assertEqual(progress['pins'], {'opentofu': CURRENT_TOFU, 'atmos': CURRENT_ATMOS})
        self.assertNotIn('pin_notice', progress)
        payload = self.receipt('generation')['payload']
        self.assertEqual((payload['pin_profile'], payload['pins']),
                         (CURRENT, {'opentofu': CURRENT_TOFU, 'atmos': CURRENT_ATMOS}))
        self.assertEqual((self.output / self.POLICY / '.tool-versions').read_text(),
                         'opentofu %s\natmos %s\n' % (CURRENT_TOFU, CURRENT_ATMOS))
        shown = [line for line in self.messages if 'OpenTofu %s' % CURRENT_TOFU in line and 'Atmos %s' % CURRENT_ATMOS in line]
        self.assertTrue(shown, self.messages)

    def test_a_v1_context_says_plainly_that_it_reproduces_legacy_pins(self):
        progress = self.generated(LEGACY)
        self.assertIn('generation', progress['verified_completed'])
        self.assertEqual(progress['pin_profile'], LEGACY)
        self.assertEqual(progress['pins'], {'opentofu': LEGACY_TOFU, 'atmos': LEGACY_ATMOS})
        self.assertIn(LEGACY_NOTICE_WORDS, progress['pin_notice'])
        self.assertEqual((self.output / self.POLICY / '.tool-versions').read_text(),
                         'opentofu %s\natmos %s\n' % (LEGACY_TOFU, LEGACY_ATMOS))
        self.assertTrue([line for line in self.messages if line.startswith('Legacy pins:') and LEGACY_NOTICE_WORDS in line],
                        self.messages)
        # A receipt made under the legacy pins keeps the shape the frozen journeys have: the label is a reading of the
        # context, shown in the progress and the messages, never a new field in an old record.
        self.assertNotIn('pin_profile', self.receipt('generation')['payload'])

    def test_a_complete_journey_runs_the_modeled_executor_under_the_profile_of_its_project(self):
        for profile, version in ((CURRENT, CURRENT_TOFU), (LEGACY, LEGACY_TOFU)):
            with self.subTest(profile=profile):
                self.setUp()
                self.use(profile)
                result = self.run_flow(self.BEFORE + self._base.AFTER_GENERATE)
                self.assertEqual(result['status'], 'complete_simulation', result)
                self.assertEqual(json.loads(self.work('main.tf.json').read_text())['terraform']['required_version'], '= ' + version)
                self.assertEqual(json.loads(self.work('plan.json').read_text())['terraform_version'], version)
                progress = self.api().reconstruct_progress(self.session)
                self.assertEqual(progress['verified_completed'], list(self.api().STAGES))
                self.assertEqual(progress['pin_profile'], profile)



# ---------------------------------------------------------------------------------------------------------------------
# Item 1c: plan review takes the engine version of either profile and labels it.
# ---------------------------------------------------------------------------------------------------------------------
def minimal_plan(version, prior_version=None):
    document = {'format_version': '1.2', 'terraform_version': version, 'planned_values': {'root_module': {}},
                'resource_changes': [], 'configuration': {'root_module': {}}}
    if prior_version is not None:
        document['prior_state'] = {'format_version': '1.0', 'terraform_version': prior_version, 'values': {'root_module': {}}}
    return document


class PlanReviewTests(unittest.TestCase):
    def codes(self, report):
        return [item['code'] for item in report['blockers']]

    def test_a_plan_of_the_current_engine_version_passes_the_version_check_and_is_labelled(self):
        from intune_iac.execution import review_plan
        report = review_plan(minimal_plan(CURRENT_TOFU, CURRENT_TOFU))
        self.assertNotIn('unqualified_engine_version', self.codes(report))
        self.assertNotIn('unqualified_prior_state_version', self.codes(report))
        self.assertEqual(report['pin_profile'], CURRENT)
        self.assertNotIn('pin_notice', report)
        self.assertFalse(report['execution_authorized'])

    def test_a_plan_of_the_legacy_engine_version_is_reproduction_only_and_says_so(self):
        from intune_iac.execution import review_plan
        report = review_plan(minimal_plan(LEGACY_TOFU, LEGACY_TOFU))
        self.assertNotIn('unqualified_engine_version', self.codes(report))
        self.assertEqual(report['pin_profile'], LEGACY)
        self.assertIn(LEGACY_NOTICE_WORDS, report['pin_notice'])

    def test_any_other_engine_version_stays_refused_and_unlabelled(self):
        from intune_iac.execution import review_plan
        for version in ('1.13.2', '1.13.0', '1.9.0', '1.10.1', '1.14.0', '', None, 1.13, ['1.13.1']):
            with self.subTest(version=version):
                report = review_plan(minimal_plan(version))
                # A value that is not even a string cannot be compared and blocks as an invalid document.
                self.assertTrue({'unqualified_engine_version', 'invalid_plan_document'} & set(self.codes(report)))
                if type(version) is not list:
                    self.assertIn('unqualified_engine_version', self.codes(report))
                self.assertEqual(report['status'], 'blocked')
                self.assertIsNone(report['pin_profile'])

    def test_the_prior_state_must_name_the_same_engine_version_as_the_plan(self):
        from intune_iac.execution import review_plan
        for plan_version, prior_version in ((CURRENT_TOFU, LEGACY_TOFU), (LEGACY_TOFU, CURRENT_TOFU), (CURRENT_TOFU, '1.13.2')):
            with self.subTest(plan=plan_version, prior=prior_version):
                self.assertIn('unqualified_prior_state_version',
                              self.codes(review_plan(minimal_plan(plan_version, prior_version))))

    def test_the_local_output_review_admits_the_same_two_versions_and_no_other(self):
        from intune_iac import execution
        from intune_iac.io import AppError
        base = {'format_version': '1.2', 'planned_values': {'root_module': {}}, 'resource_changes': [],
                'configuration': {'root_module': {'outputs': {}}}}
        for version in (CURRENT_TOFU, LEGACY_TOFU):
            document = dict(base, terraform_version=version,
                            prior_state={'format_version': '1.0', 'terraform_version': version, 'values': {'root_module': {}}})
            execution.review_local_output_plan(document, engine_version=version)
        with self.assertRaises(AppError):
            execution.review_local_output_plan(dict(base, terraform_version='1.13.2'), engine_version='1.13.2')

    def test_the_pair_is_the_one_in_pin_profiles(self):
        from intune_iac import execution, pin_profiles
        self.assertEqual(execution.ENGINE_VERSIONS, frozenset({LEGACY_TOFU, CURRENT_TOFU}))
        self.assertEqual(execution.ENGINE_PROFILES, {LEGACY_TOFU: LEGACY, CURRENT_TOFU: CURRENT})
        self.assertEqual(pin_profiles.engine_profiles(), execution.ENGINE_PROFILES)


# ---------------------------------------------------------------------------------------------------------------------
# Item 1d: the modeled executor names the engine version of the profile of the project it executes.
# ---------------------------------------------------------------------------------------------------------------------
class ModeledExecutorTests(unittest.TestCase):
    def executor(self, **keywords):
        from intune_iac import protected
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / 'executor'
        return protected.create_synthetic_executor(root, initial_value={'a': 1}, desired_value={'a': 2}, **keywords), root

    def plan_version(self, executor, root):
        from intune_iac import protected
        protected.prepare_native_operation(executor)
        return json.loads((root / 'work/plan.json').read_text())['terraform_version']

    def test_an_executor_made_without_a_version_is_the_legacy_one_with_the_frozen_manifest_shape(self):
        executor, root = self.executor()
        self.assertEqual(self.plan_version(executor, root), LEGACY_TOFU)
        self.assertEqual(json.loads((root / 'work/main.tf.json').read_text())['terraform']['required_version'], '= ' + LEGACY_TOFU)
        self.assertNotIn('engine_version', json.loads((root / 'executor.json').read_text()))

    def test_an_executor_made_for_the_current_profile_plans_and_validates_with_the_current_version(self):
        from intune_iac import protected
        executor, root = self.executor(engine_version=CURRENT_TOFU)
        self.assertEqual(self.plan_version(executor, root), CURRENT_TOFU)
        self.assertEqual(json.loads((root / 'work/main.tf.json').read_text())['terraform']['required_version'], '= ' + CURRENT_TOFU)
        protected.SyntheticExecutor(root)  # reopens: configuration, manifest and worker script agree

    def test_the_review_of_a_modeled_plan_is_labelled_by_its_version(self):
        from intune_iac import protected
        from intune_iac.execution import review_plan
        for version, profile in ((CURRENT_TOFU, CURRENT), (LEGACY_TOFU, LEGACY)):
            with self.subTest(version=version):
                executor, root = self.executor(engine_version=version)
                protected.prepare_native_operation(executor)
                report = review_plan(json.loads((root / 'work/plan.json').read_text()))
                self.assertEqual(report['pin_profile'], profile)
                self.assertNotIn('unqualified_engine_version', [item['code'] for item in report['blockers']])

    def test_an_unknown_version_is_refused_before_anything_is_created(self):
        from intune_iac import protected
        from intune_iac.io import AppError
        for version in ('1.13.2', '1.9.0', '', 1.13):
            with self.subTest(version=version):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary) / 'executor'
                    with self.assertRaises(AppError):
                        protected.create_synthetic_executor(root, initial_value={}, desired_value={}, engine_version=version)
                    self.assertFalse(root.exists())

    def test_a_manifest_version_that_the_configuration_does_not_name_is_refused(self):
        from intune_iac import protected
        from intune_iac.io import AppError
        _, root = self.executor(engine_version=CURRENT_TOFU)
        manifest = json.loads((root / 'executor.json').read_text())
        manifest['engine_version'] = LEGACY_TOFU
        (root / 'executor.json').write_text(json.dumps(manifest))
        with self.assertRaises(AppError):
            protected.SyntheticExecutor(root)
        manifest['engine_version'] = '1.13.2'
        (root / 'executor.json').write_text(json.dumps(manifest))
        with self.assertRaises(AppError):
            protected.SyntheticExecutor(root)


# ---------------------------------------------------------------------------------------------------------------------
# Item 1e: the protected worker admits the engine version of a modeled plan under a v2 context.
# ---------------------------------------------------------------------------------------------------------------------
class WorkerAdmissionOfModeledPlanTests(unittest.TestCase):
    """Offline, no binary: the worker state admission against the version a modeled executor writes in its plan.

    The contract is the real ComputedNativeStateWriteContract of the worker state tests, with the engine version of its
    baseline and plan replaced by the one a modeled plan carries (round 1 read it from the tool versions file)."""
    from plugin_tests import test_worker_state_r4 as _worker
    setUp = _worker.WorkerStateTests.setUp
    capability = _worker.WorkerStateTests.capability
    check = _worker.WorkerStateTests.check
    assert_code = _worker.WorkerStateTests.assert_code
    contract = _worker.WorkerStateTests.contract

    def modeled_version(self, version):
        from intune_iac import protected
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'executor'
            executor = protected.create_synthetic_executor(root, initial_value={'a': 1}, desired_value={'a': 2},
                                                           engine_version=version)
            protected.prepare_native_operation(executor)
            return json.loads((root / 'work/plan.json').read_text())['terraform_version']

    def test_the_worker_admits_the_engine_version_of_a_current_modeled_plan(self):
        version = self.modeled_version(CURRENT_TOFU)
        self.assertEqual(version, CURRENT_TOFU)

        def pin(document):
            document['terraform_version'] = version
        contract, *_ = self.contract(mutate_plan=pin, mutate_baseline=pin)
        self.assertIsNotNone(contract)

    def test_the_worker_still_refuses_the_engine_version_of_a_legacy_modeled_plan(self):
        version = self.modeled_version(LEGACY_TOFU)
        self.assertEqual(version, LEGACY_TOFU)

        def pin(document):
            document['terraform_version'] = version
        self.assert_code('worker_state_profile_unsupported', lambda: self.contract(mutate_plan=pin, mutate_baseline=pin))


# ---------------------------------------------------------------------------------------------------------------------
# Item 1f: the workflow store follows the profile of its provider evidence.
# ---------------------------------------------------------------------------------------------------------------------
class WorkflowProviderEvidenceTests(unittest.TestCase):
    from evaluations import test_repaired_workflow as _workflow
    setUp = _workflow.Workflow.setUp
    tearDown = _workflow.Workflow.tearDown
    write = _workflow.Workflow.write
    seed = _workflow.Workflow.seed

    def session(self, engine_version, atmos_version):
        from reference import workflow
        self.seed('partial_generate')
        (self.root / 'session.json').unlink()
        (self.root / 'receipt-index.json').unlink()
        source = json.loads((self.root / 'source.json').read_text())
        chosen = '22222222-2222-4222-8222-222222222222'
        for c in source['collections']:
            if c['kind'] == 'settings' and c['owner_id'] == chosen:
                c['pages'][0]['body']['value'][0]['settingInstance']['settingDefinitionId'] = 'unqualified_definition'
        self.write('source.json', source)
        d = json.loads((self.root / 'decisions.json').read_text())
        d['payload']['ownership'] = [{'object_id': chosen, 'writer': 'this_repository', 'owner': 'developer'}]
        self.write('decisions.json', d)
        from reference.core import normalize
        self.write('normalized.json', normalize(source, chosen, d['payload']['tenant_id']))
        self.root.joinpath('lock.hcl').write_text('provider "registry.terraform.io/deploymenttheory/microsoft365" { version = "1.0.0" }')
        self.write('provider-schema.json', {'schema_version': '2.0.0', 'provider_source': 'deploymenttheory/microsoft365',
                   'provider_version': '1.0.0', 'api_version': 'beta', 'qualification': 'offline_configuration_only',
                   'contract_sha256': workflow.sha(workflow.canonical(workflow._contract('provider-settings')))})
        self.root.joinpath('tofu.bin').write_bytes(b'synthetic tofu identity')
        self.root.joinpath('atmos.bin').write_bytes(b'synthetic atmos identity')
        self.write('provider.json', {'schema_version': '2.0.0', 'kind': 'provider_evidence', 'payload': {
            'provider_source': 'deploymenttheory/microsoft365', 'provider_version': '1.0.0', 'api_version': 'beta',
            'engine_version': engine_version, 'atmos_version': atmos_version, 'lock_path': 'lock.hcl',
            'schema_path': 'provider-schema.json', 'engine_path': 'tofu.bin', 'atmos_path': 'atmos.bin',
            'engine_sha256': workflow.sha((self.root / 'tofu.bin').read_bytes()),
            'atmos_sha256': workflow.sha((self.root / 'atmos.bin').read_bytes())}})
        rows = [('repository_context', 'repository.json'), ('source', 'source.json'), ('decisions', 'decisions.json'),
                ('normalized', 'normalized.json'), ('provider_evidence', 'provider.json')]
        return workflow.create(self.root, 'partial_generate', rows)

    def test_the_store_pairs_are_the_pairs_of_native_pins(self):
        from reference import workflow
        self.assertEqual(workflow.TOOL_PAIRS, ((LEGACY_TOFU, LEGACY_ATMOS), (CURRENT_TOFU, CURRENT_ATMOS)))

    def test_the_store_accepts_the_pair_of_either_profile(self):
        from reference import workflow
        for engine, atmos in ((LEGACY_TOFU, LEGACY_ATMOS), (CURRENT_TOFU, CURRENT_ATMOS)):
            with self.subTest(engine=engine, atmos=atmos):
                self.setUp()
                session = self.session(engine, atmos)
                self.assertEqual(session['completed'], workflow.STAGES[:6])

    def test_the_store_refuses_a_mixed_or_unknown_pair(self):
        from reference import workflow
        for engine, atmos in ((CURRENT_TOFU, LEGACY_ATMOS), (LEGACY_TOFU, CURRENT_ATMOS), ('1.13.2', CURRENT_ATMOS),
                              (CURRENT_TOFU, '1.230.2')):
            with self.subTest(engine=engine, atmos=atmos):
                self.setUp()
                session = self.session(engine, atmos)
                self.assertNotIn('mapping', session['completed'])
                self.assertNotEqual(session['completed'], workflow.STAGES[:6])


if __name__ == '__main__':
    unittest.main()
