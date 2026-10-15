"""P3c: the versioned pin migration, generation side.

Step 1 (target descriptor schema v2), step 2 (generation by context version), step 3 (golden projects, oracles) and
step 4 (help, docs, manifest). The pins are never typed twice here: every expectation about the current pins is read
from native_pins.py, and every expectation about the legacy pins is read from its legacy entries.

History stays readable and execution stays strict: nothing in this module touches the P3a frozen fixtures, and a
version-1 document or context is only ever read, labelled legacy_reproduction_only, never written back as version 2.
"""
import copy
import datetime as dt
import json
import unittest
from unittest.mock import patch

from intune_iac import native_pins
from plugin_tests import test_target as base

CURRENT = 'current_local_qualification'
LEGACY = 'legacy_reproduction_only'


def _pin(pins, profile):
    (sha, entry), = [(sha, entry) for sha, entry in pins.items() if entry['profile'] == profile]
    return sha, entry['version']


CURRENT_TOFU_SHA, CURRENT_TOFU = _pin(native_pins.OPENTOFU_PINS, CURRENT)
CURRENT_ATMOS_SHA, CURRENT_ATMOS = _pin(native_pins.ATMOS_PINS, CURRENT)
LEGACY_TOFU_SHA, LEGACY_TOFU = _pin(native_pins.OPENTOFU_PINS, LEGACY)
LEGACY_ATMOS_SHA, LEGACY_ATMOS = _pin(native_pins.ATMOS_PINS, LEGACY)


def v2_descriptor():
    document = base.fixture()
    document['schema_version'] = 'target-evidence/2.0'
    toolchain = document['binding']['toolchain']
    toolchain.update(atmos_version=CURRENT_ATMOS, atmos_sha256=CURRENT_ATMOS_SHA,
                     engine_version=CURRENT_TOFU, engine_sha256=CURRENT_TOFU_SHA)
    return document


class TargetDescriptorV2Tests(unittest.TestCase):
    def setUp(self):
        from intune_iac import target
        self.target = target
        clock = patch('intune_iac.target._now', return_value=base.NOW)
        clock.start()
        self.addCleanup(clock.stop)

    def test_a_v2_descriptor_with_the_current_pins_is_consistent_and_labelled_current(self):
        result = self.target.inspect_target(v2_descriptor())
        self.assertTrue(result['valid'], result['issues'])
        self.assertEqual(result['schema_version'], 'target-evidence/2.0')
        self.assertEqual(result['pin_profile'], CURRENT)
        self.assertFalse(result['execution_authorized'])

    def test_the_v2_toolchain_is_exactly_the_current_pins_from_native_pins(self):
        for field, wrong in (('atmos_version', LEGACY_ATMOS), ('engine_version', LEGACY_TOFU),
                             ('atmos_sha256', LEGACY_ATMOS_SHA), ('engine_sha256', LEGACY_TOFU_SHA),
                             ('atmos_sha256', 'b' * 64), ('engine_sha256', 'c' * 64)):
            with self.subTest(field=field, wrong=wrong):
                document = v2_descriptor()
                document['binding']['toolchain'][field] = wrong
                result = self.target.inspect_target(document)
                self.assertFalse(result['valid'])
                self.assertIn('/binding/toolchain/' + field, [issue['path'] for issue in result['issues']])

    def test_a_v1_descriptor_still_loads_and_says_it_is_for_reproduction_only(self):
        document = base.fixture()
        before = copy.deepcopy(document)
        result = self.target.inspect_target(document)
        self.assertTrue(result['valid'], result['issues'])
        self.assertEqual(result['schema_version'], 'target-evidence/1.0')
        self.assertEqual(result['pin_profile'], LEGACY)
        self.assertEqual(document, before)
        self.assertNotIn('target-evidence/2.0', json.dumps(result))

    def test_the_legacy_pins_are_the_legacy_entries_of_native_pins(self):
        toolchain = base.fixture()['binding']['toolchain']
        self.assertEqual((toolchain['atmos_version'], toolchain['engine_version']), (LEGACY_ATMOS, LEGACY_TOFU))

    def test_versions_do_not_mix(self):
        mixed = base.fixture()
        mixed['binding']['toolchain'].update(atmos_version=CURRENT_ATMOS, engine_version=CURRENT_TOFU)
        self.assertFalse(self.target.inspect_target(mixed)['valid'])
        relabelled = v2_descriptor()
        relabelled['schema_version'] = 'target-evidence/1.0'
        self.assertFalse(self.target.inspect_target(relabelled)['valid'])
        legacy_in_v2 = base.fixture()
        legacy_in_v2['schema_version'] = 'target-evidence/2.0'
        self.assertFalse(self.target.inspect_target(legacy_in_v2)['valid'])

    def test_an_unrecognised_version_is_invalid_and_has_no_profile(self):
        document = v2_descriptor()
        document['schema_version'] = 'target-evidence/3.0'
        result = self.target.inspect_target(document)
        self.assertFalse(result['valid'])
        self.assertIsNone(result['pin_profile'])
        self.assertIn('/schema_version', [issue['path'] for issue in result['issues']])

    def test_every_other_v2_field_is_still_checked(self):
        for path, old in base.leaves(v2_descriptor()):
            for null in (False, True):
                if null and old is None:
                    continue
                with self.subTest(path=path, null=null):
                    mutated = v2_descriptor()
                    parent = mutated
                    for key in path[:-1]:
                        parent = parent[key]
                    if null:
                        parent[path[-1]] = None
                    else:
                        del parent[path[-1]]
                    self.assertFalse(self.target.inspect_target(mutated)['valid'])

    def test_compare_labels_each_side_and_never_matches_across_versions(self):
        legacy = self.target.compare_targets(base.fixture(), base.fixture())
        self.assertEqual(legacy['status'], 'match')
        self.assertEqual((legacy['expected']['pin_profile'], legacy['observed']['pin_profile']), (LEGACY, LEGACY))
        current = self.target.compare_targets(v2_descriptor(), v2_descriptor())
        self.assertEqual(current['status'], 'match')
        self.assertEqual(current['expected']['pin_profile'], CURRENT)
        across = self.target.compare_targets(base.fixture(), v2_descriptor())
        self.assertEqual(across['status'], 'mismatch')
        self.assertIn({'path': '/schema_version', 'reason': 'changed'}, across['differences'])
        self.assertFalse(across['execution_authorized'])

    def test_reading_a_v1_descriptor_through_the_cli_writes_nothing(self):
        import tempfile
        from pathlib import Path
        from intune_iac import cli
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'legacy.target.json'
            path.write_text(json.dumps(base.fixture(), sort_keys=True), encoding='utf-8')
            before = path.read_bytes()
            before_names = sorted(p.name for p in Path(temporary).iterdir())
            result = cli._target_command(type('Args', (), {'target_command': 'inspect', 'input': str(path)})())
            self.assertEqual(result['pin_profile'], LEGACY)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(sorted(p.name for p in Path(temporary).iterdir()), before_names)

    def test_the_native_context_report_carries_the_label(self):
        from intune_iac import native_context
        legacy = native_context.inspect_native_context(base.fixture())
        self.assertEqual(legacy['target']['pin_profile'], LEGACY)
        current = native_context.inspect_native_context(v2_descriptor())
        self.assertEqual(current['target']['pin_profile'], CURRENT)
        self.assertFalse(current['execution_authorized'])

    def test_an_invalid_document_reports_no_profile_and_no_values(self):
        for document in (None, [], {'schema_version': float('nan')}):
            result = self.target.inspect_target(document)
            self.assertFalse(result['valid'])
            self.assertIsNone(result['pin_profile'])



# ---------------------------------------------------------------------------------------------------------------------
# Step 2: generation chooses its pins by the context schema version; version 1 is reproduction only.
# ---------------------------------------------------------------------------------------------------------------------
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTEXT_V1, CONTEXT_V2 = '1.0.0', '2.0.0'


def minor_ceiling(version):
    major, minor, _ = version.split('.')
    return '%s.%d.0' % (major, int(minor) + 1)


def with_pins(context, profile, explicit=True):
    """A copy of a context under one profile; explicit False leaves the pin fields out (repository contexts do)."""
    value = copy.deepcopy(context)
    for key in ('engine', 'engine_version', 'atmos_version', 'provider_source', 'provider_version'):
        value.pop(key, None)
    value['schema_version'] = CONTEXT_V2 if profile == CURRENT else CONTEXT_V1
    if explicit:
        tofu, atmos = (CURRENT_TOFU, CURRENT_ATMOS) if profile == CURRENT else (LEGACY_TOFU, LEGACY_ATMOS)
        value.update(engine='tofu', engine_version=tofu, atmos_version=atmos,
                     provider_source='deploymenttheory/microsoft365', provider_version='1.0.0')
    return value


class EngineCase(unittest.TestCase):
    """Runs the public engine functions on temporary files only."""

    def stage(self, source, context):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        (folder / 'source.json').write_text(json.dumps(source))
        (folder / 'context.json').write_text(json.dumps(context))
        return folder / 'source.json', folder / 'context.json', folder / 'project'

    def production_inputs(self):
        from plugin_tests.test_production import inputs
        return inputs()

    def synthetic_inputs(self):
        source = json.loads((ROOT / 'examples/supported/input/export.json').read_text())
        context = json.loads((ROOT / 'examples/context.json').read_text())
        return source, context


class ProductionGenerationTests(EngineCase):
    def candidate(self, output):
        files = list(output.rglob('main.tf.txt'))
        self.assertEqual(len(files), 1)
        return files[0].read_text()

    def generate(self, context):
        from intune_iac.engine import generate, inspect_source, verify_project
        source, _ = self.production_inputs()
        src, ctx, output = self.stage(source, context)
        review = inspect_source(src, ctx)
        result = generate(src, ctx, output)
        self.assertTrue(verify_project(src, ctx, output)['preservation_verified'])
        return review, result, output

    def base(self):
        return self.production_inputs()[1]

    def test_a_current_context_generates_the_current_engine_pin_and_says_so(self):
        for explicit in (True, False):
            with self.subTest(explicit=explicit):
                review, result, output = self.generate(with_pins(self.base(), CURRENT, explicit))
                self.assertIn('required_version = "= %s"' % CURRENT_TOFU, self.candidate(output))
                self.assertNotIn(LEGACY_TOFU, self.candidate(output))
                for report in (review, result):
                    self.assertEqual(report['pin_profile'], CURRENT)
                    self.assertEqual(report['pins'], {'opentofu': CURRENT_TOFU, 'atmos': CURRENT_ATMOS})
                    self.assertNotIn('pin_notice', report)
                self.assertFalse(result['execution_authorized'])

    def test_a_v1_context_reproduces_the_legacy_output_and_the_report_says_so(self):
        for explicit in (True, False):
            with self.subTest(explicit=explicit):
                review, result, output = self.generate(with_pins(self.base(), LEGACY, explicit))
                self.assertIn('required_version = "= %s"' % LEGACY_TOFU, self.candidate(output))
                for report in (review, result):
                    self.assertEqual(report['pin_profile'], LEGACY)
                    self.assertEqual(report['pins'], {'opentofu': LEGACY_TOFU, 'atmos': LEGACY_ATMOS})
                    self.assertIn('reproduce earlier output only', report['pin_notice'])

    def test_a_v1_context_file_is_never_rewritten_by_inspect_generate_or_verify(self):
        from intune_iac.engine import generate, inspect_source, verify_project
        source, _ = self.production_inputs()
        src, ctx, output = self.stage(source, with_pins(self.base(), LEGACY))
        before = (src.read_bytes(), ctx.read_bytes())
        inspect_source(src, ctx)
        generate(src, ctx, output)
        verify_project(src, ctx, output)
        self.assertEqual((src.read_bytes(), ctx.read_bytes()), before)
        self.assertEqual(json.loads(ctx.read_text())['schema_version'], CONTEXT_V1)

    def test_pins_that_the_context_version_does_not_select_are_refused(self):
        from intune_iac.engine import generate
        from intune_iac.io import AppError
        mixed = [with_pins(self.base(), CURRENT), with_pins(self.base(), LEGACY)]
        mixed[0].update(engine_version=LEGACY_TOFU)
        mixed[1].update(atmos_version=CURRENT_ATMOS)
        third = with_pins(self.base(), CURRENT)
        third['schema_version'] = '3.0.0'
        for context in mixed + [third]:
            with self.subTest(version=context['schema_version'], engine=context['engine_version'], atmos=context['atmos_version']):
                src, ctx, output = self.stage(self.production_inputs()[0], context)
                with self.assertRaises(AppError) as raised:
                    generate(src, ctx, output)
                self.assertEqual(raised.exception.code, 'invalid_context')
                self.assertFalse(output.exists())

    def test_the_oracle_expects_the_pins_the_context_selects(self):
        """A project made under one profile does not verify under the other: the independent oracle disagrees."""
        from intune_iac.engine import generate, verify_project
        from intune_iac.io import AppError
        source, _ = self.production_inputs()
        for made, read in ((LEGACY, CURRENT), (CURRENT, LEGACY)):
            with self.subTest(made=made, read=read):
                src, ctx, output = self.stage(source, with_pins(self.base(), made))
                generate(src, ctx, output)
                ctx.write_text(json.dumps(with_pins(self.base(), read)))
                with self.assertRaises(AppError) as raised:
                    verify_project(src, ctx, output)
                self.assertEqual(raised.exception.code, 'postcondition_failed')

    def test_the_production_oracle_names_a_required_version_of_the_other_profile(self):
        from intune_iac import engine, production, production_oracle
        source, _ = self.production_inputs()
        raw = json.dumps(source).encode()
        for made, read in ((CURRENT, LEGACY), (LEGACY, CURRENT)):
            with self.subTest(made=made, read=read):
                context = with_pins(self.base(), made)
                normalized = production.normalize(source, context)
                files = engine._expected_files(raw, source, context, normalized)
                self.assertEqual(production_oracle.compare(raw, normalized, context=context, files=files), [])
                other = with_pins(self.base(), read)
                self.assertIn('production_hcl_changed',
                              production_oracle.compare(raw, production.normalize(source, other), context=other, files=files))


class SyntheticGenerationTests(EngineCase):
    def generate(self, context):
        from intune_iac.engine import generate, inspect_source, verify_project
        source, _ = self.synthetic_inputs()
        src, ctx, output = self.stage(source, context)
        review = inspect_source(src, ctx)
        result = generate(src, ctx, output)
        self.assertTrue(verify_project(src, ctx, output)['preservation_verified'])
        return review, result, output

    def base(self):
        return self.synthetic_inputs()[1]

    def test_a_current_context_generates_the_current_tool_versions_and_range(self):
        review, result, output = self.generate(with_pins(self.base(), CURRENT))
        self.assertEqual((output / '.tool-versions').read_text(), 'opentofu %s\natmos %s\n' % (CURRENT_TOFU, CURRENT_ATMOS))
        main = (output / 'components/terraform/intune-reference/main.tf').read_text()
        self.assertIn('required_version = ">= %s, < %s"' % (CURRENT_TOFU, minor_ceiling(CURRENT_TOFU)), main)
        for report in (review, result):
            self.assertEqual(report['pin_profile'], CURRENT)
            self.assertEqual(report['pins'], {'opentofu': CURRENT_TOFU, 'atmos': CURRENT_ATMOS})

    def test_a_v1_context_reproduces_the_legacy_project_and_says_so(self):
        review, result, output = self.generate(with_pins(self.base(), LEGACY))
        self.assertEqual((output / '.tool-versions').read_text(), 'opentofu %s\natmos %s\n' % (LEGACY_TOFU, LEGACY_ATMOS))
        main = (output / 'components/terraform/intune-reference/main.tf').read_text()
        self.assertIn('required_version = ">= %s, < %s"' % (LEGACY_TOFU, minor_ceiling(LEGACY_TOFU)), main)
        for report in (review, result):
            self.assertEqual(report['pin_profile'], LEGACY)
            self.assertIn('reproduce earlier output only', report['pin_notice'])

    def test_mixed_or_unknown_versions_are_refused_before_anything_is_written(self):
        from intune_iac.engine import generate
        from intune_iac.io import AppError
        for change in ({'engine_version': LEGACY_TOFU}, {'atmos_version': LEGACY_ATMOS}, {'schema_version': '3.0.0'},
                       {'schema_version': CONTEXT_V1}):
            with self.subTest(change=change):
                context = dict(with_pins(self.base(), CURRENT), **change)
                src, ctx, output = self.stage(self.synthetic_inputs()[0], context)
                with self.assertRaises(AppError):
                    generate(src, ctx, output)
                self.assertFalse(output.exists())

    def test_the_reference_oracle_checks_the_tool_versions_and_range_of_the_context_profile(self):
        from intune_iac import engine
        from reference.core import normalize
        from reference.invariants import compare
        source, base = self.synthetic_inputs()
        raw = json.dumps(source).encode()
        normalized = normalize(source, base['selected_policy_id'], base['tenant_id'])
        for made, other in ((CURRENT, LEGACY), (LEGACY, CURRENT)):
            with self.subTest(made=made):
                context = with_pins(base, made)
                files = engine._expected_files(raw, source, context, normalized)
                self.assertEqual(compare(raw, normalized, files=files, context=context), [])
                wrong = with_pins(base, other)
                errors = compare(raw, normalized, files=files, context=wrong)
                self.assertIn('generated_tool_versions_changed', errors)
                self.assertIn('generated_provider_changed', errors)
                tampered = dict(files, **{'.tool-versions': 'opentofu 9.9.9\natmos 9.9.9\n'})
                self.assertIn('generated_tool_versions_changed', compare(raw, normalized, files=tampered, context=context))

    def test_a_generated_repository_carries_exactly_the_pins_of_native_pins(self):
        _, _, output = self.generate(with_pins(self.base(), CURRENT))
        tools = dict(line.split(' ') for line in (output / '.tool-versions').read_text().split('\n') if line)
        self.assertEqual(tools, {'opentofu': CURRENT_TOFU, 'atmos': CURRENT_ATMOS})
        current = {entry['version'] for pins in (native_pins.OPENTOFU_PINS, native_pins.ATMOS_PINS)
                   for entry in pins.values() if entry['profile'] == CURRENT}
        self.assertEqual(set(tools.values()), current)


class WorkerAdmissionOfGeneratedPinsTests(unittest.TestCase):
    """Offline: the protected worker's state and plan admission against the engine version a generated project names.

    No binary is run. The contract is built from the worker state tests' own fixtures, with the baseline and plan
    engine version replaced by the version parsed from a project this package generated.
    """
    from plugin_tests import test_worker_state_r4 as _worker
    setUp = _worker.WorkerStateTests.setUp
    capability = _worker.WorkerStateTests.capability
    check = _worker.WorkerStateTests.check
    assert_code = _worker.WorkerStateTests.assert_code
    contract = _worker.WorkerStateTests.contract

    def generated_engine_version(self, profile):
        from intune_iac.engine import generate
        source = json.loads((ROOT / 'examples/supported/input/export.json').read_text())
        context = with_pins(json.loads((ROOT / 'examples/context.json').read_text()), profile)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / 's.json').write_text(json.dumps(source))
            (folder / 'c.json').write_text(json.dumps(context))
            generate(folder / 's.json', folder / 'c.json', folder / 'project')
            line = [l for l in (folder / 'project/.tool-versions').read_text().split('\n') if l.startswith('opentofu ')]
        return line[0].split(' ')[1]

    def test_the_worker_admits_the_engine_version_of_a_current_project(self):
        version = self.generated_engine_version(CURRENT)
        self.assertEqual(version, CURRENT_TOFU)

        def pin(document):
            document['terraform_version'] = version
        contract, *_ = self.contract(mutate_plan=pin, mutate_baseline=pin)
        self.assertIsNotNone(contract)

    def test_the_worker_refuses_the_engine_version_of_a_legacy_project(self):
        version = self.generated_engine_version(LEGACY)
        self.assertEqual(version, LEGACY_TOFU)

        def pin(document):
            document['terraform_version'] = version
        self.assert_code('worker_state_profile_unsupported', lambda: self.contract(mutate_plan=pin, mutate_baseline=pin))


class SyntheticEstateContextTests(unittest.TestCase):
    def test_a_new_estate_names_the_current_pins_in_every_context(self):
        from intune_iac import synthetic
        estate = synthetic.generate_estate(seed=7, policy_count=2)
        self.assertEqual(len(estate['contexts']), 2)
        for context in estate['contexts']:
            self.assertEqual((context['schema_version'], context['engine_version'], context['atmos_version']),
                             (CONTEXT_V2, CURRENT_TOFU, CURRENT_ATMOS))

    def test_a_written_estate_generates_under_the_current_pins(self):
        from intune_iac import synthetic
        from intune_iac.engine import generate
        with tempfile.TemporaryDirectory() as temporary:
            paths = synthetic.write_estate(Path(temporary) / 'estate', seed=7, policy_count=1)
            result = generate(paths['capture'], paths['context'], Path(temporary) / 'project')
            self.assertEqual(result['pin_profile'], CURRENT)
            self.assertEqual((Path(temporary) / 'project/.tool-versions').read_text(),
                             'opentofu %s\natmos %s\n' % (CURRENT_TOFU, CURRENT_ATMOS))


class WizardContextTests(unittest.TestCase):
    def selection(self, profile, **change):
        context = with_pins(json.loads((ROOT / 'examples/context.json').read_text()), profile)
        context.update(change)
        return context

    def test_the_selection_check_accepts_each_version_with_its_own_pins_and_no_mix(self):
        from intune_iac.io import AppError
        from intune_iac.wizard import _validate_selection_context
        for profile in (CURRENT, LEGACY):
            _validate_selection_context(self.selection(profile))
        for context in (self.selection(CURRENT, engine_version=LEGACY_TOFU), self.selection(CURRENT, atmos_version=LEGACY_ATMOS),
                        self.selection(LEGACY, engine_version=CURRENT_TOFU), self.selection(LEGACY, atmos_version=CURRENT_ATMOS),
                        self.selection(CURRENT, schema_version='3.0.0')):
            with self.subTest(context=(context['schema_version'], context['engine_version'], context['atmos_version'])):
                with self.assertRaises(AppError) as raised:
                    _validate_selection_context(context)
                self.assertEqual(raised.exception.code, 'unsupported_selection_context')

    def test_the_wizard_pins_are_the_current_pins_of_native_pins(self):
        import ast
        tree = ast.parse((ROOT / 'intune_iac/wizard.py').read_text(encoding='utf-8'))
        found = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == '_validate_selection_context':
                for statement in ast.walk(node):
                    if isinstance(statement, ast.Assign) and getattr(statement.targets[0], 'id', None) in ('pinned', 'legacy'):
                        found[statement.targets[0].id] = ast.literal_eval(statement.value)
        self.assertEqual({k: found['pinned'][k] for k in ('schema_version', 'engine_version', 'atmos_version')},
                         {'schema_version': CONTEXT_V2, 'engine_version': CURRENT_TOFU, 'atmos_version': CURRENT_ATMOS})
        self.assertEqual({k: found['legacy'][k] for k in ('schema_version', 'engine_version', 'atmos_version')},
                         {'schema_version': CONTEXT_V1, 'engine_version': LEGACY_TOFU, 'atmos_version': LEGACY_ATMOS})

    def test_a_new_repository_context_is_version_2_and_omits_the_pin_fields(self):
        from plugin_tests.test_wizard_repository import RepositoryWizardTests, POLICY
        case = RepositoryWizardTests('test_repository_target_creates_owned_context_without_context_prompt')
        case.setUp()
        try:
            case.run_script(['deploy/dev', 'policy', POLICY, 'review'])
            context = case.context()
        finally:
            case.doCleanups()
        self.assertEqual(context['schema_version'], CONTEXT_V2)
        for key in ('engine', 'engine_version', 'atmos_version', 'provider_source', 'provider_version'):
            self.assertNotIn(key, context)

class IndependentOracleLiteralTests(unittest.TestCase):
    """The oracles spell their own pins; these tests are the one place that ties them to native_pins.py."""

    def test_every_literal_equals_the_native_pins_profile_of_its_context_version(self):
        from intune_iac import production_oracle
        from reference import core, invariants
        expected = {CONTEXT_V1: (LEGACY_TOFU, LEGACY_ATMOS), CONTEXT_V2: (CURRENT_TOFU, CURRENT_ATMOS)}
        self.assertEqual(set(production_oracle._TOOL_PINS), set(expected))
        self.assertEqual(set(core.TOOL_PINS), set(expected))
        self.assertEqual(set(invariants.TOOL_PROFILES), set(expected))
        for version, (tofu, atmos) in expected.items():
            with self.subTest(version=version):
                self.assertEqual(production_oracle._TOOL_PINS[version], (tofu, atmos))
                self.assertEqual((core.TOOL_PINS[version]['engine'], core.TOOL_PINS[version]['atmos']), (tofu, atmos))
                range_text = '>= %s, < %s' % (tofu, minor_ceiling(tofu))
                self.assertEqual(core.TOOL_PINS[version]['required_version'], range_text)
                self.assertEqual(invariants.TOOL_PROFILES[version],
                                 {'tool_versions': 'opentofu %s\natmos %s\n' % (tofu, atmos), 'required_version': range_text})

    def test_the_producer_profiles_come_from_native_pins(self):
        from intune_iac import pin_profiles
        self.assertEqual(pin_profiles.CONTEXT_PROFILES, {CONTEXT_V1: LEGACY, CONTEXT_V2: CURRENT})
        for version, profile in ((CONTEXT_V1, LEGACY), (CONTEXT_V2, CURRENT)):
            selected = pin_profiles.context_profile({'schema_version': version})
            tofu, atmos = (CURRENT_TOFU, CURRENT_ATMOS) if profile == CURRENT else (LEGACY_TOFU, LEGACY_ATMOS)
            self.assertEqual((selected['profile'], selected['engine_version'], selected['atmos_version']), (profile, tofu, atmos))
        for unknown in (None, [], {}, {'schema_version': 2}, {'schema_version': ['1.0.0']}, {'schema_version': '3.0.0'}):
            self.assertIsNone(pin_profiles.context_profile(unknown))
        self.assertEqual(pin_profiles.context_pin_report({'schema_version': CONTEXT_V2, 'engine_version': LEGACY_TOFU}),
                         {'pin_profile': None})


class MaintainedRepositoryComponentTests(EngineCase):
    """A repository made under the legacy pins stays readable by the consumer contract; nothing else is accepted."""

    def component(self, profile):
        from intune_iac.engine import generate
        source, base = self.synthetic_inputs()
        src, ctx, output = self.stage(source, with_pins(base, profile))
        generate(src, ctx, output)
        folder = output / 'components/terraform/intune-reference'
        return {path.name: path.read_text() for path in folder.iterdir()}, base

    def errors(self, sources, base, **keywords):
        from reference.core import stable_key
        from reference.invariants import component_errors
        key = stable_key(base['tenant_id'], base['selected_policy_id'])
        return component_errors(sources, key, base['selected_policy_id'], **keywords)

    def test_either_profiles_component_is_accepted_without_a_context_and_a_changed_range_is_not(self):
        for profile in (CURRENT, LEGACY):
            with self.subTest(profile=profile):
                sources, base = self.component(profile)
                self.assertEqual(self.errors(sources, base), [])
        sources, base = self.component(CURRENT)
        changed = {name: text.replace('>= %s, < %s' % (CURRENT_TOFU, minor_ceiling(CURRENT_TOFU)), '>= 1.12.0, < 1.13.0')
                   for name, text in sources.items()}
        self.assertIn('generated_provider_changed', self.errors(changed, base))

    def test_a_named_required_version_accepts_only_that_profile(self):
        sources, base = self.component(CURRENT)
        current_range = '>= %s, < %s' % (CURRENT_TOFU, minor_ceiling(CURRENT_TOFU))
        legacy_range = '>= %s, < %s' % (LEGACY_TOFU, minor_ceiling(LEGACY_TOFU))
        self.assertEqual(self.errors(sources, base, required_version=current_range, any_known_profile=False), [])
        self.assertIn('generated_provider_changed',
                      self.errors(sources, base, required_version=legacy_range, any_known_profile=False))
        self.assertIn('generated_provider_changed', self.errors(sources, base, any_known_profile=False))



# ---------------------------------------------------------------------------------------------------------------------
# Step 3: the example context and the golden expected projects, regenerated for the pin change only.
# ---------------------------------------------------------------------------------------------------------------------
VARIANTS = ('supported', 'partial', 'missing-page', 'access-denied')
ACTIVE_VARIANTS = ('supported',)
PIN_FILES = {'.tool-versions', 'components/terraform/intune-reference/main.tf', 'review/proposed-component.tf.txt'}


def legacy_range():
    return '>= %s, < %s' % (LEGACY_TOFU, minor_ceiling(LEGACY_TOFU))


def current_range():
    return '>= %s, < %s' % (CURRENT_TOFU, minor_ceiling(CURRENT_TOFU))


def tree(base):
    base = Path(base)
    return {p.relative_to(base).as_posix(): p.read_text(encoding='utf-8') for p in sorted(base.rglob('*')) if p.is_file()}


class ExampleContextTests(unittest.TestCase):
    def test_the_example_context_is_version_2_with_the_current_pins_of_native_pins(self):
        context = json.loads((ROOT / 'examples/context.json').read_text())
        self.assertEqual((context['schema_version'], context['engine'], context['engine_version'], context['atmos_version']),
                         (CONTEXT_V2, 'tofu', CURRENT_TOFU, CURRENT_ATMOS))

    def test_the_example_context_passes_the_wizard_selection_check(self):
        from intune_iac.wizard import _validate_selection_context
        _validate_selection_context(json.loads((ROOT / 'examples/context.json').read_text()))


class GoldenProjectTests(EngineCase):
    """The golden projects change for the pin change only: nothing else in them may move."""

    def generate(self, variant, profile):
        from intune_iac.engine import generate
        # The example input is copied byte for byte: the golden source receipt records its byte digest.
        context = with_pins(json.loads((ROOT / 'examples/context.json').read_text()), profile)
        src, ctx, output = self.stage({}, context)
        src.write_bytes((ROOT / 'examples' / variant / 'input/export.json').read_bytes())
        generate(src, ctx, output)
        return tree(output)

    def test_each_golden_project_is_what_the_current_context_generates_byte_for_byte(self):
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                self.assertEqual(tree(ROOT / 'examples' / variant / 'expected/project'),
                                 self.generate(variant, CURRENT))

    def test_the_golden_projects_name_the_current_pins_and_not_the_legacy_ones(self):
        for variant in VARIANTS:
            expected = tree(ROOT / 'examples' / variant / 'expected/project')
            with self.subTest(variant=variant):
                pinned = [name for name in expected if name in PIN_FILES]
                self.assertTrue(pinned)
                for name in pinned:
                    if name == '.tool-versions':
                        self.assertEqual(expected[name], 'opentofu %s\natmos %s\n' % (CURRENT_TOFU, CURRENT_ATMOS))
                    else:
                        self.assertIn('required_version = "%s"' % current_range(), expected[name])
                joined = '\n'.join(expected.values())
                for legacy in (LEGACY_TOFU, LEGACY_ATMOS):
                    self.assertNotIn(legacy, joined)

    def test_the_only_difference_from_the_legacy_projects_is_the_pin_text(self):
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                legacy, current = self.generate(variant, LEGACY), self.generate(variant, CURRENT)
                self.assertEqual(sorted(legacy), sorted(current))
                changed = {name for name in legacy if legacy[name] != current[name]}
                self.assertEqual(changed - {'generated-files.json'}, PIN_FILES & set(legacy))
                for name in changed - {'generated-files.json'}:
                    restored = (current[name].replace(current_range(), legacy_range())
                                .replace('opentofu ' + CURRENT_TOFU, 'opentofu ' + LEGACY_TOFU)
                                .replace('atmos ' + CURRENT_ATMOS, 'atmos ' + LEGACY_ATMOS))
                    self.assertEqual(restored, legacy[name], name)
                self.assertIn('generated-files.json', changed)

    def test_the_azure_integration_project_repeats_the_supported_pins(self):
        supported = tree(ROOT / 'examples/supported/expected/project')
        azure = tree(ROOT / 'examples/azure-integration/expected/project')
        for name in ('.tool-versions', 'components/terraform/intune-reference/main.tf'):
            self.assertEqual(azure[name], supported[name], name)
        manifest = json.loads(azure['generated-files.json'])['files']
        import hashlib
        for name in ('.tool-versions', 'components/terraform/intune-reference/main.tf'):
            self.assertEqual(manifest[name], hashlib.sha256(azure[name].encode()).hexdigest(), name)


if __name__ == '__main__':
    unittest.main()
