#!/usr/bin/env python3
"""Exercise repository discovery, candidate generation and MCP from another cwd.

All capture contents are constructed offline. No tenant, provider or model call.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    plugin = Path(args.plugin).resolve()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    repo = out/'repository'
    (repo/'stacks/deploy').mkdir(parents=True)
    (repo/'components/terraform/policy').mkdir(parents=True)
    (repo/'atmos.yaml').write_text('stacks:\n  base_path: stacks\n  included_paths: ["deploy/**/*"]\ncomponents:\n  terraform:\n    base_path: components/terraform\n    command: tofu\n')
    (repo/'stacks/base.yaml').write_text('components:\n  terraform:\n    base:\n      metadata: {type: abstract}\n      vars: {region: west, list: [one, two]}\n')
    (repo/'stacks/deploy/dev.yaml').write_text('import: [base]\ncomponents:\n  terraform:\n    policy:\n      metadata: {inherits: [base]}\n      vars: {list: [three]}\n      env: {TOKEN: offline-secret-canary}\n')
    (repo/'components/terraform/policy/main.tf').write_text('# existing repository fixture\n')
    capture = json.loads((plugin/'examples/supported/input/export.json').read_text())
    capture.update(synthetic=False, exporter={'id': 'intune-iac-settings-catalog-graph', 'version': '1.0.0'}, references=[], ownership=[])
    for assignment in capture['collections'][2]['pages'][0]['body']['value']:
        assignment.update(source='direct', sourceId=None)
    policy_id = capture['collections'][0]['pages'][0]['body']['value'][0]['id']
    source = out/'offline-capture.json'
    source.write_text(json.dumps(capture))
    session = out/'session.json'
    project = out/'candidate'
    logs = out/'logs'
    logs.mkdir()
    checks = []

    def run(name, argv, expected=0, stdin=None):
        proc = subprocess.run([sys.executable, str(plugin/'scripts/intune-iac.py'), *map(str, argv)],
                              cwd=out, input=stdin, text=True, capture_output=True, timeout=60)
        (logs/(name+'.stdout')).write_text(proc.stdout)
        (logs/(name+'.stderr')).write_text(proc.stderr)
        if proc.returncode != expected:
            raise AssertionError(f'{name}: expected exit {expected}, got {proc.returncode}; inspect logs')
        checks.append({'name': name, 'exit_code': proc.returncode})
        return proc

    discovery = json.loads(run('discover', ['repository', 'inspect', '--root', repo]).stdout)
    assert discovery['status'] == 'discovered'
    resolution = json.loads(run('resolve', ['repository', 'resolve', '--root', repo, '--stack', 'deploy/dev', '--component', 'policy']).stdout)
    assert resolution['status'] == 'resolved' and 'effective' not in resolution
    assert 'offline-secret-canary' not in json.dumps(resolution)
    wizard = run('wizard', ['wizard', '--session', session, '--repo', repo, '--input', source,
                            '--stack', 'deploy/dev', '--component', 'policy', '--output', project],
                 stdin=policy_id+'\ngenerate\nfinish\n')
    final = json.loads(wizard.stdout.splitlines()[-1])
    assert final['status'] == 'complete'
    state = json.loads(session.read_text())
    result = json.loads(run('verify', ['verify', '--input', source, '--context', state['paths']['context'], '--output', project]).stdout)
    assert result['preservation_verified'] is True
    assert list(project.rglob('main.tf.txt')) and not list(project.rglob('*.tf'))
    assert json.loads((project/'commands/command-cards.json').read_text())['cards'] == []
    params = out/'parameters.json'
    params.write_text(json.dumps({'root': str(repo), 'stack': 'deploy/dev', 'component': 'policy'}))
    receipts = out/'receipts'
    preview = json.loads(run('preview', ['action', 'preview', 'repository_resolve', '--parameters', params, '--state-dir', receipts]).stdout)
    assert preview['status'] == 'ready' and not receipts.exists()
    executed = json.loads(run('local-action', ['action', 'run', 'repository_resolve', '--parameters', params, '--state-dir', receipts]).stdout)
    assert executed['status'] == 'succeeded_verified'
    assert executed['result']['source_fingerprint'] == resolution['source_fingerprint']
    requests = [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18',
            'capabilities': {}, 'clientInfo': {'name': 'repository-qualification', 'version': '1'}}},
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'intune_repository_resolve',
          'arguments': {'root': str(repo), 'stack': 'deploy/dev', 'component': 'policy'}}},
    ]
    response = run('mcp', ['mcp', '--read-root', repo], stdin='\n'.join(map(json.dumps, requests))+'\n')
    assert 'offline-secret-canary' not in response.stdout
    assert json.loads(response.stdout.splitlines()[-1])['result']['isError'] is False
    report = {'version': 1, 'passed': len(checks), 'checks': checks, 'fixture_origin': 'constructed_offline',
              'candidate_manifest_sha256': hashlib.sha256((project/'generated-files.json').read_bytes()).hexdigest(),
              'source_fingerprint': resolution['source_fingerprint'], 'cloud_calls': 0, 'provider_calls': 0,
              'scope': 'Actual local CLI, repository-first wizard, candidate verification, action runner and stdio MCP.'}
    (out/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
