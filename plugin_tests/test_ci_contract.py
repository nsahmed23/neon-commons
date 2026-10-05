"""CI permission, failure propagation and archive validation regressions."""
import copy
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/validate.yml'
PINS = {
    'checkout': 'actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803',
    'python': 'actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97',
    'evidence': 'actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f',
}
ORDER = ['checkout', 'python', 'platform', 'dependencies', 'verify', 'smoke', 'release', 'extract', 'extracted', 'evidence']


def contract_issues(document):
    """Enforce this validation workflow's narrow security/quality contract."""
    issues = []
    if not isinstance(document, dict): return ['invalid_workflow']
    if set(document.get('on', {})) != {'push', 'pull_request', 'workflow_dispatch'}: issues.append('events')
    if document.get('permissions') != {'contents': 'read'}: issues.append('permissions')
    if document.get('defaults', {}).get('run', {}).get('shell') != 'bash --noprofile --norc -euo pipefail {0}': issues.append('shell')
    jobs = document.get('jobs', {})
    if set(jobs) != {'validate'}: return issues + ['jobs']
    job = jobs['validate']
    if job.get('runs-on') != 'ubuntu-24.04': issues.append('runner')
    if any(k in job for k in ('permissions', 'environment', 'secrets', 'uses', 'container', 'services', 'if', 'continue-on-error')): issues.append('job_scope')
    if type(job.get('timeout-minutes')) is not int or not 1 <= job['timeout-minutes'] <= 30: issues.append('timeout')
    steps = job.get('steps', [])
    if [step.get('id') for step in steps] != ORDER: return issues + ['step_order']
    indexed = {step['id']: step for step in steps}
    for name, reference in PINS.items():
        if indexed[name].get('uses') != reference: issues.append('action_pin')
    if indexed['checkout'].get('with', {}).get('persist-credentials') is not False: issues.append('credentials')
    python = indexed['python'].get('with', {})
    if python.get('python-version') != '3.12.14' or python.get('architecture') != 'x64' or python.get('check-latest') is not False: issues.append('python')
    if python.get('cache'): issues.append('cache')
    for step in steps:
        if 'continue-on-error' in step or step.get('if') and step['id'] != 'evidence': issues.append('suppressed_gate')
        if step['id'] not in PINS and ('uses' in step or not isinstance(step.get('run'), str)): issues.append('unreviewed_action')
        if any(token in step.get('run', '') for token in ('|| true', 'set +e', 'exit 0', 'continue-on-error')): issues.append('suppressed_exit')
    text = json.dumps(document)
    if re.search(r'secrets\.|id-token|pull_request_target|workflow_run|self-hosted|azure/login|aws-actions/configure|terraform apply|tofu apply|terraform import|tofu import', text): issues.append('external_authority')
    dep = indexed['dependencies'].get('run', '')
    for required in ('--require-hashes', '--only-binary=:all:', '--no-index', 'verify-dependencies.py', 'requirements-runtime-linux-x86_64-cp312.lock'):
        if required not in dep: issues.append('dependency_gate')
    if dep.count('--require-hashes') != 2: issues.append('dependency_hashes')
    verify = indexed['verify'].get('run', '')
    if 'scripts/verify-plugin.py --include-core' not in verify or 'raise SystemExit' not in verify: issues.append('full_verifier')
    for script in ('qualify-workflow.py', 'qualify-repository.py', 'qualify-terminal.py'):
        if script not in indexed['smoke'].get('run', ''): issues.append('smoke')
    if 'scripts/build-release.py' not in indexed['release'].get('run', ''): issues.append('release')
    if 'check-archives.py' not in indexed['extract'].get('run', ''): issues.append('archive_gate')
    if not re.search(r'verify-plugin\.py"? --include-core', indexed['extracted'].get('run', '')): issues.append('extracted_gate')
    artifact = indexed['evidence']
    if artifact.get('if') != '${{ always() }}': issues.append('failure_evidence')
    options = artifact.get('with', {})
    if options.get('include-hidden-files') is not False or options.get('overwrite') is not False: issues.append('artifact_scope')
    if options.get('if-no-files-found') != 'error' or options.get('retention-days') != 7: issues.append('artifact_retention')
    return sorted(set(issues))


class CIContractTests(unittest.TestCase):
    def workflow(self):
        self.assertTrue(WORKFLOW.is_file(), 'release-validation workflow is absent')
        return yaml.safe_load(WORKFLOW.read_text())

    def test_actual_yaml_contract(self):
        self.assertEqual(contract_issues(self.workflow()), [])

    def test_dangerous_workflow_mutations_are_rejected(self):
        original = self.workflow()
        mutations = [lambda x: x.update(permissions={'contents': 'write'}),
            lambda x: x['on'].update(pull_request_target={}),
            lambda x: x['jobs']['validate'].update(**{'runs-on': 'self-hosted'}),
            lambda x: x['jobs']['validate'].update(**{'continue-on-error': True}),
            lambda x: x['jobs']['validate']['steps'][0]['with'].update(**{'persist-credentials': True}),
            lambda x: x['jobs']['validate']['steps'][0].update(uses='actions/checkout@v6'),
            lambda x: x['jobs']['validate']['steps'][4].update(**{'if': '${{ false }}'}),
            lambda x: x['jobs']['validate']['steps'][4].update(run='python scripts/verify-plugin.py --include-core || true'),
            lambda x: x['jobs']['validate'].update(env={'TOKEN': '${{ secrets.AZURE_TOKEN }}'}),
            lambda x: x['jobs']['validate']['steps'][3].update(run='python -m pip install -r requirements-runtime.txt'),
            lambda x: x['jobs']['validate']['steps'][6].update(run='tofu apply -auto-approve'),
            lambda x: x['jobs']['validate']['steps'][-1]['with'].update(**{'include-hidden-files': True})]
        for mutate in mutations:
            document = copy.deepcopy(original); mutate(document)
            self.assertTrue(contract_issues(document))

    def test_full_verifier_failure_and_false_success_receipt_propagate(self):
        document = self.workflow(); script = next(s['run'] for s in document['jobs']['validate']['steps'] if s['id'] == 'verify')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); bin_path = root / 'bin'; bin_path.mkdir()
            wrapper = bin_path / 'python'
            wrapper.write_text('#!' + sys.executable + '\n' + '''import json,os,pathlib,sys
if len(sys.argv)>1 and sys.argv[1].endswith("verify-plugin.py"):
 root=pathlib.Path(os.environ["CI_ROOT"])/"verification";root.mkdir(parents=True,exist_ok=True)
 mode=os.environ["CI_CASE"]
 report={"success":mode=="pass","tests":1,"passed":1,"failures":0,"errors":0,"skipped":0,"core_regressions_included":True}
 if mode=="skip":report.update(success=True,skipped=1,passed=0)
 if mode=="boolean_counts":report.update(success=True,passed=True,failures=False,errors=False,skipped=False)
 (root/"result.json").write_text(json.dumps(report))
 raise SystemExit(7 if mode=="nonzero" else 0)
os.execv(sys.executable,[sys.executable,*sys.argv[1:]])
''')
            wrapper.chmod(0o700)
            for mode in ('nonzero', 'false_receipt', 'skip', 'boolean_counts', 'pass'):
                env = dict(os.environ, PATH=str(bin_path) + os.pathsep + os.environ['PATH'], CI_ROOT=str(root / mode), CI_CASE=mode)
                result = subprocess.run(['bash', '--noprofile', '--norc', '-euo', 'pipefail', '-c', script], env=env, cwd=ROOT, capture_output=True, timeout=15)
                self.assertEqual(result.returncode == 0, mode == 'pass', (mode, result.stderr.decode()))

    def test_shell_scripts_are_syntactically_valid(self):
        for step in self.workflow()['jobs']['validate']['steps']:
            if 'run' in step:
                result = subprocess.run(['bash', '-n'], input=step['run'], text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, step['id'])


class CIArchiveTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / 'research/enterprise-ci/check-archives.py'
        self.assertTrue(path.is_file(), 'CI archive checker is absent')
        spec = importlib.util.spec_from_file_location('ci_archives', path)
        self.api = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.api)
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def archive(self, files=None, extra=None):
        files = files or {'README.md': b'candidate only\n'}
        path = self.root / 'candidate.zip'
        hashes = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n' for name, data in files.items()).encode()
        with zipfile.ZipFile(path, 'w') as z:
            for name, data in dict(files, SHA256SUMS=hashes).items(): z.writestr('intune-iac/' + name, data)
            if extra:
                with warnings.catch_warnings():
                    warnings.filterwarnings('ignore', message='Duplicate name:.*', category=UserWarning)
                    z.writestr(*extra)
        return path

    def test_valid_archive_hashes_checked_before_extraction(self):
        path = self.archive(); data = self.api.verify_archive(path, 'intune-iac')
        self.assertEqual(data['README.md'], b'candidate only\n')
        self.assertEqual(set(data), {'README.md', 'SHA256SUMS'})

    def test_unsafe_symlink_unlisted_and_duplicate_members_rejected(self):
        link = zipfile.ZipInfo('intune-iac/link'); link.create_system = 3; link.external_attr = (stat.S_IFLNK | 0o777) << 16
        for extra in [('../outside', b'bad'), ('intune-iac/extra', b'bad'), (link, b'../bad'), ('intune-iac/README.md', b'duplicate')]:
            path = self.archive(extra=extra)
            with self.assertRaises(ValueError): self.api.verify_archive(path, 'intune-iac')

    def test_manifest_does_not_hide_changed_bytes(self):
        path = self.archive()
        with zipfile.ZipFile(path) as z: entries = {n: z.read(n) for n in z.namelist()}
        entries['intune-iac/README.md'] = b'tampered'
        with zipfile.ZipFile(path, 'w') as z:
            for name, data in entries.items(): z.writestr(name, data)
        with self.assertRaises(ValueError): self.api.verify_archive(path, 'intune-iac')
