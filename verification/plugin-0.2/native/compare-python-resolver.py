"""Prepare byte-matched inert fixtures and compare existing native receipts to Python.

Native receipts with a python-shared-* name must be generated separately with the
qualified isolated runner. This script never launches native commands.
"""
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, '/workspace/scratch/26b6d364cfda/intune-iac-plugin')
import yaml
from intune_iac.repository import resolve_component

ROOT = Path(__file__).resolve().parent
CASES = ['imports_ab', 'imports_ba', 'inherits_parent_b', 'inherits_parent_a', 'scope_local', 'scope_override', 'empty_values', 'type_change', 'parent_to_child', 'child_to_override', 'null_shapes']


class LiteralDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    return [{'path': p.relative_to(root).as_posix(), 'sha256': sha(p)} for p in sorted(root.rglob('*')) if p.is_file()]


results = []
for case in CASES:
    original = ROOT/'fixtures'/case
    shared = ROOT/'python-fixtures'/case
    if not shared.exists():
        shutil.copytree(original, shared)
        path = shared/'atmos.yaml'
        cfg = yaml.safe_load(path.read_text())
        # Runtime control configuration is excluded from this literal resolver;
        # every manifest/HCL byte and retained configuration value stays unchanged.
        for key in ('settings', 'version', 'templates', 'logs'):
            cfg.pop(key, None)
        path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    if case == 'child_to_override':
        manifest = shared/'stacks/orgs/qualification.yaml'
        manifest.write_text(yaml.dump(yaml.safe_load(manifest.read_text()), Dumper=LiteralDumper, sort_keys=False))
    original_files = inventory(original)
    shared_files = inventory(shared)
    original_map = {x['path']: x['sha256'] for x in original_files}
    shared_map = {x['path']: x['sha256'] for x in shared_files}
    differences = [path for path in sorted(set(original_map)|set(shared_map)) if original_map.get(path) != shared_map.get(path)]
    expected_differences = ['atmos.yaml', 'stacks/orgs/qualification.yaml'] if case == 'child_to_override' else ['atmos.yaml']
    assert differences == expected_differences, (case, differences)
    report = resolve_component(shared, 'orgs/qualification', 'leaf')
    native_path = ROOT/('atmos-python-shared-'+case+'.json')
    native = json.loads(native_path.read_text()) if native_path.exists() else None
    native_vars = None
    if native and native['returncode'] == 0:
        native_vars = json.loads(native['stdout'])['vars']
    row = {'case': case, 'physical_stack': 'orgs/qualification', 'component': 'leaf', 'input_directory': str(shared), 'source_fingerprint': report['source_fingerprint'], 'resolver_sources': report['sources'], 'complete_fixture_sources': shared_files, 'original_fixture_sources': original_files, 'differences_from_original': differences, 'python_status': report['status'], 'python_blockers': report['blockers'], 'python_vars': report.get('effective', {}).get('vars'), 'native_receipt': native_path.name if native else None, 'native_returncode': native['returncode'] if native else None, 'native_vars': native_vars}
    if native:
        row['native_receipt_sha256'] = sha(native_path)
        row['exact_sources_match'] = sorted(native['source_manifest'], key=lambda x: x['path']) == shared_files and native['source_unchanged'] is True
        row['passed'] = (report['status'] == 'blocked' and any(b['code'] == 'merge_type_conflict' for b in report['blockers']) and native['returncode'] != 0 and 'mergo merge failed' in native.get('stderr', '')) if case == 'type_change' else (report['status'] == 'resolved' and native['returncode'] == 0 and report['effective']['vars'] == native_vars)
        row['passed'] = row['passed'] and row['exact_sources_match']
    else:
        row['passed'] = None
    results.append(row)
output = {'schema_version': '1.0', 'adapter': 'atmos-literal/1.0', 'purpose': 'Narrow exact-input native-vs-Python literal vars equivalence; no identity or execution qualification.', 'fixture_preparation': 'Original fixtures copied, atmos.yaml runtime settings/version/templates/logs removed; child_to_override generated YAML alias expanded to equivalent literal duplicate mapping. Native and Python both consume the prepared shared directory. All original versus prepared file hashes retained.', 'python_implementation_sha256': sha(Path('/workspace/scratch/26b6d364cfda/intune-iac-plugin/intune_iac/repository.py')), 'native_release': 'Atmos 1.199.0', 'native_binary_sha256': sha(ROOT/'bin/atmos'), 'cases': results, 'all_passed': all(row['passed'] is True for row in results)}
(ROOT/'atmos-python-comparison.json').write_text(json.dumps(output, indent=2)+'\n')
print(json.dumps({'receipt': str(ROOT/'atmos-python-comparison.json'), 'cases': [{key: row[key] for key in ('case', 'python_status', 'native_returncode', 'passed')} for row in results], 'all_passed': output['all_passed']}, indent=2))
