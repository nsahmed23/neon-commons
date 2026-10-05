import json
from pathlib import Path
import shutil
import subprocess
import sys
import yaml

root = Path(__file__).resolve().parent
env = json.loads((root / 'atmos-version.json').read_text())['environment']
old = {'empty_string': 'old', 'zero': 7, 'false': True, 'null_value': 'old', 'empty_list': ['old'], 'empty_map': {'old': 'old'}}
new = {'empty_string': '', 'zero': 0, 'false': False, 'null_value': None, 'empty_list': [], 'empty_map': {}}
results = []
cases = []
for stage in ['parent_to_child', 'child_to_override']:
    parents = {'parent': {'metadata': {'type': 'abstract'}, 'vars': old}}
    child = {'metadata': {'component': 'demo', 'inherits': ['parent']}, 'vars': new if stage == 'parent_to_child' else old}
    if stage == 'child_to_override': child['overrides'] = {'vars': new}
    cases.append((stage, {}, {'vars': {'stage': 'qualification'}, 'components': {'terraform': {**parents, 'leaf': child}}}))
cases.append(('null_shapes', {'a': {'vars': {'null_to_scalar': None, 'null_to_list': None, 'null_to_map': None, 'map_to_null': {'old': 1}, 'list_to_null': ['old'], 'scalar_to_null': 'old'}}},
              {'import': ['catalog/a'], 'vars': {'stage': 'qualification', 'null_to_scalar': 'new', 'null_to_list': ['new'], 'null_to_map': {'new': 1}, 'map_to_null': None, 'list_to_null': None, 'scalar_to_null': None}, 'components': {'terraform': {'leaf': {'metadata': {'component': 'demo'}}}}}))
for name, imports, stack in cases:
    fixture = root / 'fixtures' / name
    shutil.copytree(root / 'fixtures/imports_ab', fixture, dirs_exist_ok=True)
    for path in (fixture / 'stacks/catalog').glob('*.yaml'): path.unlink()
    for key, value in imports.items(): (fixture / 'stacks/catalog' / (key + '.yaml')).write_text(yaml.safe_dump(value, sort_keys=False))
    (fixture / 'stacks/orgs/qualification.yaml').write_text(yaml.safe_dump(stack, sort_keys=False))
    cmd = [sys.executable, str(root / 'socket-denied-exec.py'), str(root / 'bin/atmos'), 'describe', 'component', 'leaf', '-s', 'qualification', '--format', 'json', '--process-functions=false', '--process-templates=false']
    p = subprocess.run(cmd, cwd=fixture, env=env, capture_output=True, text=True, timeout=30, close_fds=True)
    result = {'argv': cmd, 'cwd': str(fixture), 'environment': env, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
    (root / ('atmos-' + name + '.json')).write_text(json.dumps(result, indent=2))
    results.append({'case': name, 'returncode': p.returncode, 'vars': json.loads(p.stdout).get('vars') if p.returncode == 0 else None, 'stderr': p.stderr})
(root / 'atmos-empty-supplement-summary.json').write_text(json.dumps(results, indent=2))
print(json.dumps(results, indent=2))
