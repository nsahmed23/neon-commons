"""Self-authored literal fixtures and native offline qualification receipts."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parent
REPO = Path('/workspace/scratch/26b6d364cfda/intune-iac-plugin')
FIXTURES = ROOT / 'fixtures'
FIXTURES.mkdir(exist_ok=True)
RUNTIME_BIN = ROOT / 'runtime-bin'
RUNTIME_BIN.mkdir(exist_ok=True)
FIXTURE_HOME = ROOT / 'fixture-home'
FIXTURE_HOME.mkdir(exist_ok=True)
for name in ['config', 'cache', 'data', 'tmp']:
    (FIXTURE_HOME / name).mkdir(exist_ok=True)
# The pinned Atmos homedir package calls getent when HOME is absent. This
# self-authored fixture adapter supplies only a fixture home, avoiding any HOME
# assignment and preventing automatic discovery of the real user's config.
getent = RUNTIME_BIN / 'getent'
getent.write_text('#!/bin/sh\n' + 'printf "%s\\n" ' + shlex.quote(f'fixture:x:{os.getuid()}:{os.getgid()}:fixture:{FIXTURE_HOME}:/bin/false') + '\n')
getent.chmod(0o755)
CLI = ROOT / 'empty.tofurc'
CLI.write_text('')
ENV = {
    'PATH': str(RUNTIME_BIN),
    'LANG': 'C.UTF-8',
    'TZ': 'UTC',
    'XDG_CONFIG_HOME': str(FIXTURE_HOME / 'config'),
    'XDG_CACHE_HOME': str(FIXTURE_HOME / 'cache'),
    'XDG_DATA_HOME': str(FIXTURE_HOME / 'data'),
    'TMPDIR': str(FIXTURE_HOME / 'tmp'),
    'ATMOS_TELEMETRY_ENABLED': 'false',
    'ATMOS_VERSION_CHECK_ENABLED': 'false',
    'CHECKPOINT_DISABLE': '1',
    'TF_IN_AUTOMATION': '1',
    'TF_CLI_CONFIG_FILE': str(CLI),
}

def native(name, executable, args, cwd):
    cmd = [sys.executable, str(ROOT / 'socket-denied-exec.py'), str(ROOT / 'bin' / executable), *args]
    p = subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True, timeout=45, close_fds=True)
    result = {'name': name, 'argv': cmd, 'cwd': str(cwd), 'environment': ENV,
              'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr,
              'network': 'seccomp denies socket, socketpair and connect with EPERM',
              'filesystem_isolated': False, 'credentials_inherited': False,
              'home_note': 'HOME absent; pinned Atmos getent fallback returns fixture-home via self-authored stub'}
    (ROOT / (name + '.json')).write_text(json.dumps(result, indent=2))
    print(json.dumps({'name': name, 'returncode': p.returncode, 'stdout': p.stdout[:250], 'stderr': p.stderr[:500]}), flush=True)
    return result

CONFIG = {
    'base_path': '.',
    'components': {'terraform': {'base_path': 'components/terraform', 'command': '/nonexistent/qualification-disabled',
                                'auto_generate_backend_file': False, 'apply_auto_approve': False}},
    'stacks': {'base_path': 'stacks', 'included_paths': ['orgs/*'], 'name_pattern': '{stage}'},
    'settings': {'telemetry': {'enabled': False}, 'inject_github_token': False,
                 'inject_gitlab_token': False, 'inject_bitbucket_token': False},
    'version': {'check': {'enabled': False}},
    'templates': {'settings': {'enabled': False}},
    'logs': {'level': 'Off'},
}

def make_fixture(name, imports, stack):
    d = FIXTURES / name
    (d / 'stacks/catalog').mkdir(parents=True, exist_ok=True)
    (d / 'stacks/orgs').mkdir(parents=True, exist_ok=True)
    (d / 'components/terraform/demo').mkdir(parents=True, exist_ok=True)
    (d / 'atmos.yaml').write_text(yaml.safe_dump(CONFIG, sort_keys=False))
    for key, value in imports.items():
        (d / 'stacks/catalog' / (key + '.yaml')).write_text(yaml.safe_dump(value, sort_keys=False))
    (d / 'stacks/orgs/qualification.yaml').write_text(yaml.safe_dump(stack, sort_keys=False))
    # There are intentionally no .tf files, modules, backends, providers, hooks,
    # env/auth declarations, custom YAML tags, functions or templates here.
    return d

def leaf(variables=None, inherits=None):
    metadata = {'component': 'demo'}
    if inherits is not None:
        metadata['inherits'] = inherits
    return {'metadata': metadata, 'vars': variables or {}}

CASES = []
for order in [('a', 'b'), ('b', 'a')]:
    imported = {v: {'vars': {'selected': v, 'nested': {v: v, 'same': v}, 'items': [v]}}
                for v in order}
    stack = {'import': ['catalog/' + x for x in order],
             'vars': {'stage': 'qualification', 'nested': {'local': 'local'}},
             'components': {'terraform': {'leaf': leaf()}}}
    CASES.append(('imports_' + ''.join(order), imported, stack))

for order in [('parent_a', 'parent_b'), ('parent_b', 'parent_a')]:
    parents = {v: {'metadata': {'type': 'abstract'}, 'vars': {'selected': v, 'nested': {v: v, 'same': v}, 'items': [v]}}
               for v in order}
    stack = {'vars': {'stage': 'qualification'}, 'components': {'terraform': {**parents, 'leaf': leaf({'nested': {'local': 'local'}}, list(order))}}}
    CASES.append(('inherits_' + order[-1], {}, stack))

stack = {'vars': {'stage': 'qualification', 'selected': 'root', 'nested': {'root': 'root', 'same': 'root'}},
         'terraform': {'vars': {'selected': 'type', 'nested': {'type': 'type', 'same': 'type'}}},
         'components': {'terraform': {
             'parent': {'metadata': {'type': 'abstract'}, 'vars': {'selected': 'parent', 'nested': {'parent': 'parent', 'same': 'parent'}}},
             'leaf': leaf({'selected': 'local', 'nested': {'local': 'local', 'same': 'local'}}, ['parent'])}}}
CASES.append(('scope_local', {}, copy.deepcopy(stack)))
stack['components']['terraform']['leaf']['overrides'] = {'vars': {'selected': 'override', 'nested': {'override': 'override', 'same': 'override'}}}
CASES.append(('scope_override', {}, stack))

old = {'empty_string': 'old', 'zero': 7, 'false': True, 'null_value': 'old', 'empty_list': ['old'], 'empty_map': {'old': 'old'}}
new = {'empty_string': '', 'zero': 0, 'false': False, 'null_value': None, 'empty_list': [], 'empty_map': {}}
CASES.append(('empty_values', {'a': {'vars': old}}, {'import': ['catalog/a'], 'vars': {'stage': 'qualification', **new}, 'components': {'terraform': {'leaf': leaf()}}}))
CASES.append(('type_change', {'a': {'vars': {'selected': 'scalar'}}}, {'import': ['catalog/a'], 'vars': {'stage': 'qualification', 'selected': ['list']}, 'components': {'terraform': {'leaf': leaf()}}}))

native('atmos-version', 'atmos', ['version'], ROOT)
native('tofu-version', 'tofu', ['version', '-json'], ROOT)
summary = []
for name, imports, stack in CASES:
    fixture = make_fixture(name, imports, stack)
    result = native('atmos-' + name, 'atmos', ['describe', 'component', 'leaf', '-s', 'qualification', '--format', 'json', '--process-functions=false', '--process-templates=false'], fixture)
    payload = None
    if result['returncode'] == 0:
        try: payload = json.loads(result['stdout'])
        except json.JSONDecodeError: pass
    summary.append({'case': name, 'returncode': result['returncode'], 'vars': payload.get('vars') if payload else None, 'component': payload.get('component') if payload else None})
(ROOT / 'atmos-native-summary.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2), flush=True)

for example in ['supported', 'azure-integration']:
    source = REPO / 'examples' / example / 'expected/project'
    target = FIXTURES / ('hcl-' + example)
    target.mkdir(exist_ok=True)
    for file in source.rglob('*.tf'):
        dest = target / file.relative_to(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, dest)
    native('tofu-fmt-' + example, 'tofu', ['fmt', '-check', '-diff', '-recursive', str(target)], ROOT)

inert = FIXTURES / 'hcl-inert'
inert.mkdir(exist_ok=True)
(inert / 'main.tf').write_text('terraform {\n  required_version = "= 1.10.0"\n}\n\nlocals {\n  qualification_value = "offline"\n}\n\noutput "qualification_value" {\n  value = local.qualification_value\n}\n')
native('tofu-init-inert', 'tofu', ['init', '-backend=false', '-input=false', '-no-color'], inert)
native('tofu-validate-inert', 'tofu', ['validate', '-json'], inert)

manifest = []
for file in sorted(FIXTURES.rglob('*')):
    if file.is_file(): manifest.append({'path': str(file.relative_to(ROOT)), 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()})
(ROOT / 'fixture-manifest.json').write_text(json.dumps(manifest, indent=2))
