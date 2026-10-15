"""Pre-upgrade artefacts frozen at 5d709ba, before the OpenTofu and Atmos pin migration.

plugin_tests/fixtures/pre_pin_migration holds what the product made while OpenTofu 1.10.0 and Atmos 1.199.0 were its
pins (see MANIFEST.json for the commands and GENERATE.sh for the procedure). These tests are the acceptance tests every
later migration step has to keep green: nothing here may be regenerated or re-frozen to make a later step pass.

The session, journey and adoption evidence bind absolute paths and the digests of files that contain them, so a test
copies those kinds to the manifest's fixed root (under an exclusive lock) and removes it again.
"""
import fcntl
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'pre_pin_migration'
MANIFEST = json.loads((FIXTURES / 'MANIFEST.json').read_text())
FROZEN_ROOT = Path(MANIFEST['path_bound']['root'])
LOCK = Path(str(FROZEN_ROOT) + '.lock')
POLICY = '22222222-2222-4222-8222-222222222222'
JOURNEY_POLICY = '10bd368c-bef5-5691-8fd4-235ab85f70b4'
CLI = ROOT / 'scripts/intune-iac.py'
PROJECTS = {
    'synthetic-explicit-pins': ('inputs/synthetic-export.json', 'contexts/synthetic-explicit-pins.context.json'),
    'production-explicit-pins': ('inputs/production-export.json', 'contexts/production-explicit-pins.context.json'),
    'production-omitted-pins': ('inputs/production-export.json', 'contexts/repository-omitted-pins.context.json'),
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def tree(base):
    """Relative posix path to bytes for every file under base."""
    base = Path(base)
    return {p.relative_to(base).as_posix(): p.read_bytes() for p in sorted(base.rglob('*')) if p.is_file()}


class FreezeIntegrityTests(unittest.TestCase):
    def test_every_fixture_file_equals_the_manifest(self):
        listed = MANIFEST['files']
        present = {p.relative_to(FIXTURES).as_posix() for p in FIXTURES.rglob('*') if p.is_file()}
        self.assertEqual(present - {'MANIFEST.json'}, set(listed), 'files added to or missing from the freeze')
        for name, entry in sorted(listed.items()):
            data = (FIXTURES / name).read_bytes()
            self.assertEqual((sha256(data), len(data)), (entry['sha256'], entry['size']), name)

    def test_manifest_records_the_commit_the_data_and_how_each_kind_was_made(self):
        self.assertTrue(MANIFEST['frozen_at_commit'].startswith('5d709ba'))
        self.assertIn('SYNTHETIC', MANIFEST['data'])
        self.assertIn('no network', MANIFEST['data'])
        self.assertEqual(set(MANIFEST['kinds']), {'inputs', 'contexts', 'projects', 'session', 'journey', 'adoption'})
        for name, kind in MANIFEST['kinds'].items():
            self.assertTrue(kind['how_made'], name)
        top = {name.split('/')[0] for name in MANIFEST['files']}
        self.assertEqual(top, {'inputs', 'contexts', 'projects', 'session', 'journey', 'adoption', 'GENERATE.sh'})

    def test_contexts_hold_the_legacy_pins_or_omit_them(self):
        for name in ('synthetic-explicit-pins', 'production-explicit-pins'):
            context = json.loads((FIXTURES / 'contexts' / (name + '.context.json')).read_text())
            self.assertEqual((context['engine'], context['engine_version'], context['atmos_version']),
                             ('tofu', '1.10.0', '1.199.0'), name)
        self.assertTrue(json.loads((FIXTURES / 'contexts/synthetic-explicit-pins.context.json').read_text())['source_is_synthetic'])
        omitted = json.loads((FIXTURES / 'contexts/repository-omitted-pins.context.json').read_text())
        for key in ('engine', 'engine_version', 'atmos_version', 'provider_source', 'provider_version'):
            self.assertNotIn(key, omitted)
        self.assertEqual(omitted['target_assurance'], 'repository_literal_resolution_only')
        saved = next((FIXTURES / 'session').glob('session.json.repository-context.*.json'))
        self.assertEqual(saved.read_bytes(), (FIXTURES / 'contexts/repository-omitted-pins.context.json').read_bytes())

    def test_frozen_projects_name_the_legacy_pins(self):
        synthetic = FIXTURES / 'projects/synthetic-explicit-pins'
        self.assertEqual((synthetic / '.tool-versions').read_text(), 'opentofu 1.10.0\natmos 1.199.0\n')
        self.assertIn('required_version = ">= 1.10.0, < 1.11.0"',
                      (synthetic / 'components/terraform/intune-reference/main.tf').read_text())
        for name in ('production-explicit-pins', 'production-omitted-pins'):
            project = FIXTURES / 'projects' / name
            self.assertTrue((project / 'adoption/target-receipt.json').is_file(), name)
            candidates = list(project.glob('candidates/components/terraform/*/main.tf.txt'))
            self.assertEqual(len(candidates), 1, name)
            self.assertIn('required_version = "= 1.10.0"', candidates[0].read_text(), name)


class RegenerationTests(unittest.TestCase):
    """The current code still derives the frozen project from the frozen input and context.

    No file is allowed to differ: the generators write no timestamps, random ids or absolute paths.
    """

    def stage(self, name):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        source_name, context_name = PROJECTS[name]
        source, context = base / 'source.json', base / 'context.json'
        source.write_bytes((FIXTURES / source_name).read_bytes())
        context.write_bytes((FIXTURES / context_name).read_bytes())
        return base, source, context

    def test_each_frozen_context_regenerates_the_frozen_project_byte_for_byte(self):
        from intune_iac.engine import generate
        for name in PROJECTS:
            with self.subTest(project=name):
                base, source, context = self.stage(name)
                result = generate(source, context, base / 'project')
                self.assertEqual(result['outcome'], 'succeeded_verified')
                self.assertFalse(result['execution_authorized'])
                frozen, regenerated = tree(FIXTURES / 'projects' / name), tree(base / 'project')
                self.assertEqual(sorted(regenerated), sorted(frozen))
                self.assertEqual([n for n in frozen if regenerated[n] != frozen[n]], [])
                self.assertEqual(result['manifest_sha256'], sha256(frozen['generated-files.json']))

    def test_current_verification_accepts_each_frozen_project_by_exact_bytes(self):
        from intune_iac.engine import verify_project
        for name in PROJECTS:
            with self.subTest(project=name):
                base, source, context = self.stage(name)
                shutil.copytree(FIXTURES / 'projects' / name, base / 'project')
                self.assertTrue(verify_project(source, context, base / 'project')['preservation_verified'])
                (base / 'project/README.md').write_bytes((base / 'project/README.md').read_bytes() + b'edit\n')
                from intune_iac.io import AppError
                with self.assertRaises(AppError):
                    verify_project(source, context, base / 'project')


class FrozenRootCase(unittest.TestCase):
    """Copies the path-bound kinds to the manifest root, serialised across runs, and removes them afterwards."""
    kinds = ()
    needs_interpreter = False

    def setUp(self):
        descriptor = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        self.addCleanup(os.close, descriptor)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        self.addCleanup(self.remove_root)
        self.remove_root()
        FROZEN_ROOT.mkdir(mode=0o700)
        wanted = tuple(kind + '/' for kind in self.kinds)
        for name, mode in sorted(MANIFEST['directories'].items()):
            if name in self.kinds or name.startswith(wanted):
                (FROZEN_ROOT / name).mkdir(parents=True, exist_ok=True)
                os.chmod(FROZEN_ROOT / name, int(mode, 8))
        for name, entry in sorted(MANIFEST['files'].items()):
            if name.startswith(wanted):
                target = FROZEN_ROOT / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((FIXTURES / name).read_bytes())
                os.chmod(target, int(entry['mode'], 8))
        if self.needs_interpreter:
            self.restore_interpreter()

    @staticmethod
    def remove_root():
        if not os.path.lexists(FROZEN_ROOT):
            return
        info = os.lstat(FROZEN_ROOT)
        if stat.S_ISLNK(info.st_mode) or info.st_uid != os.geteuid():
            raise RuntimeError('the fixed freeze root exists and is not a directory of this user; remove it by hand')
        shutil.rmtree(FROZEN_ROOT)

    def restore_interpreter(self):
        """The journey executor must be the running interpreter, byte for byte (protected.py SyntheticExecutor)."""
        binding = MANIFEST['interpreter_binding']
        running = Path(sys.executable).resolve()
        home = 'home = ' + str(running.parent) + '\ninclude-system-site-packages = false\n'
        if sha256(running.read_bytes()) != binding['executable_sha256'] or home != binding['pyvenv_cfg']:
            self.skipTest('the journey was frozen with CPython %s (sha256 %s, %s); this interpreter differs, and the '
                          'product refuses an executor that is not the running interpreter'
                          % (binding['python_version'], binding['executable_sha256'], binding['pyvenv_cfg'].split('\n')[0]))
        tool = FROZEN_ROOT / 'journey/session.json.journey/synthetic-executor/tool'
        shutil.copyfile(running, tool)
        os.chmod(tool, 0o500)

    def process(self, *args):
        return subprocess.run([sys.executable, '-B', str(CLI), *map(str, args)], text=True, capture_output=True,
                              cwd='/tmp', timeout=120, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))

    def call(self, *args):
        result = self.process(*args)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def unchanged(self, prefix):
        """Every frozen file under prefix still has its manifest bytes."""
        for name, entry in MANIFEST['files'].items():
            if name.startswith(prefix):
                data = (FROZEN_ROOT / name).read_bytes()
                self.assertEqual(sha256(data), entry['sha256'], name)


class SessionResumeTests(FrozenRootCase):
    kinds = ('session',)

    def resume(self):
        from intune_iac.wizard import run_wizard
        messages, answers = [], iter(['save'])
        result = run_wizard(FROZEN_ROOT / 'session/session.json', input_fn=lambda prompt: next(answers),
                            output_fn=messages.append)
        return result, messages

    def test_v1_repository_resume_never_changes_context_version_or_path(self):
        session = FROZEN_ROOT / 'session/session.json'
        before = json.loads(session.read_text())
        context_path = Path(before['paths']['context'])
        context_bytes = context_path.read_bytes()
        before_files = sorted(p.name for p in session.parent.iterdir())
        self.assertEqual((before['step'], before['generated']), ('preview', None))
        result, messages = self.resume()
        after = json.loads(session.read_text())
        self.assertEqual((result['status'], result['step'], result['generated']), ('suspended', 'preview', False))
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(after['paths']['context'], before['paths']['context'])
        self.assertEqual(after['repository'], before['repository'])
        self.assertEqual(context_path.read_bytes(), context_bytes)
        context = json.loads(context_bytes)
        self.assertEqual(context['schema_version'], '1.0.0')
        for key in ('engine', 'engine_version', 'atmos_version', 'provider_source', 'provider_version'):
            self.assertNotIn(key, context)
        # No second context was written and the generated review was not invalidated.
        self.assertEqual(sorted(n for n in (p.name for p in session.parent.iterdir()) if n not in before_files), ['attempts'])
        self.assertEqual(len(list(session.parent.glob('session.json.repository-context.*.json'))), 1)
        self.assertFalse(any('invalidated' in line or 'rebuilt' in line for line in messages), messages)
        self.assertEqual({k: after[k] for k in before}, before)

    def test_resume_leaves_every_frozen_source_byte_alone(self):
        self.resume()
        for name, entry in MANIFEST['files'].items():
            if name.startswith('session/') and not name.endswith('/session.json'):
                self.assertEqual(sha256((FROZEN_ROOT / name).read_bytes()), entry['sha256'], name)


class JourneyAdoptionTests(FrozenRootCase):
    kinds = ('journey', 'adoption')
    needs_interpreter = True

    def paths(self):
        return (FROZEN_ROOT / 'journey/session.json', FROZEN_ROOT / 'adoption/store', FROZEN_ROOT / 'adoption/handoff')

    def test_frozen_complete_journey_reconstructs_at_the_freeze_commit(self):
        from intune_iac import journey
        session = self.paths()[0]
        state = journey._load(session)
        self.assertEqual((state['mode'], state['lifecycle'], state['in_flight']), ('simulation', 'complete_simulation', None))
        observed = journey._observe(session, state)
        # P3b: the freeze commit's implementation digest is no longer the current one once a bound file has changed, so
        # the journey is read as history (implementation='recorded'); execution paths keep the strict default.
        progress = journey._progress(session, state, observed, implementation='recorded')
        self.assertIn(progress['implementation']['relation'], ('same', 'known_earlier'))
        self.assertEqual(progress['verified_completed'], list(journey.STAGES))
        self.assertEqual(progress['next_state'], 'complete_simulation')
        self.assertFalse(progress['execution_authorized'])
        self.assertIs(observed['raw_capture']['synthetic'], True)
        self.assertEqual(state['selected_ids'], [JOURNEY_POLICY])
        self.unchanged('journey/')

    def test_frozen_adoption_preview_rebuilds_the_binding_without_writing(self):
        session, store, _ = self.paths()
        preview = self.call('workbench', 'adoption-preview', '--root', store, '--session', session)
        self.assertEqual(preview['status'], 'ready_local_model_handoff')
        self.assertFalse(preview['execution_authorized'])
        self.assertFalse(preview['cloud_authority'])
        binding = preview['binding']
        self.assertEqual(binding['object_ids'], [JOURNEY_POLICY])
        self.assertFalse(binding['native_provider_execution'])
        self.assertFalse(binding['cloud_execution'])
        self.assertEqual(binding['evidence_class'], 'reconstructed_local_synthetic_adoption')
        self.unchanged('journey/')

    def test_frozen_adoption_verifies_and_is_idempotent(self):
        session, store, handoff = self.paths()
        lineage = self.call('workbench', 'adoption-lineage', '--root', store, '--object', JOURNEY_POLICY)
        self.assertEqual(len(lineage['adoptions']), 1)
        recorded = lineage['adoptions'][0]['data']
        journal = json.loads((handoff / 'adoption.json').read_text())
        self.assertEqual(journal['status'], 'complete')
        self.assertEqual(recorded['binding_sha256'], journal['binding_sha256'])
        # Re-running adopt on a complete handoff reconstructs the journey again and checks the saved artefact,
        # collection run and observations; it must not replay anything.
        result = self.call('workbench', 'adopt', '--root', store, '--session', session, '--output', handoff)
        self.assertEqual(result['status'], 'adopted_local_model')
        self.assertEqual(result['binding_sha256'], journal['binding_sha256'])
        self.assertEqual(result['object_ids'], [JOURNEY_POLICY])
        self.assertFalse(result['execution_authorized'])
        self.assertFalse(result['remote_import_performed'])
        self.assertTrue(result['original_journey_preserved'])
        self.assertEqual(json.loads((handoff / 'adoption.json').read_text()), journal)
        self.unchanged('journey/')


if __name__ == '__main__':
    unittest.main()
