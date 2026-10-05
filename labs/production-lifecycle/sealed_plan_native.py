#!/usr/bin/env python3
"""Native OpenTofu saved-plan immutability proof using local outputs only."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from intune_iac import provider_execution as pe
from intune_iac.io import digest, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tofu', required=True); parser.add_argument('--work', required=True); parser.add_argument('--receipt', required=True)
    args = parser.parse_args(); tofu = Path(args.tofu).resolve(strict=True)
    if pe._sha(tofu, pe.MAX_BINARY) != pe.PRODUCTION_PINS.tofu_sha256: raise ValueError('OpenTofu pin mismatch')
    work = Path(args.work).absolute(); work.mkdir(mode=0o700, parents=False, exist_ok=False)
    write_json(work / 'main.tf.json', {'terraform': {'required_version': '= 1.10.0'}, 'output': {'proof': {'value': 'approved-sealed-plan'}}})
    (work / 'tofu.rc').write_text('disable_checkpoint = true\nprovider_installation { filesystem_mirror { path = "./no-providers" } }\n')
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(work), 'TF_CLI_CONFIG_FILE': str(work / 'tofu.rc'),
           'TF_IN_AUTOMATION': '1', 'TF_INPUT': '0', 'CHECKPOINT_DISABLE': '1'}
    commands = []
    def run(label, tail, fds=()):
        result = pe._supervise([str(tofu), *tail], cwd=work, env=env, executable=str(tofu), pass_fds=fds)
        commands.append({'label': label, 'exit_code': result['code'], 'stdout_sha256': digest(result['stdout'].decode())})
        if result['code'] != 0: raise ValueError('Native local output command failed: '+label)
        return result['stdout']
    run('init', ['init', '-input=false', '-no-color', '-backend=false'])
    run('plan', ['plan', '-input=false', '-no-color', '-out=approved.plan'])
    approved = pe._sha(work / 'approved.plan'); fd = pe._sealed_plan(work / 'approved.plan', approved)
    protected = {}
    try:
        (work / 'approved.plan').write_bytes(b'in-place attacker replacement after review')
        protected['original_file_changed'] = pe._sha(work / 'approved.plan') != approved
        for name, attempt in [('descriptor_write', lambda: os.write(fd, b'evil')), ('truncate', lambda: os.ftruncate(fd, 0))]:
            try: attempt()
            except PermissionError: protected[name] = 'denied'
            else: raise AssertionError('Sealed snapshot accepted mutation')
        run('apply-sealed-snapshot', ['apply', '-input=false', '-no-color', '/proc/self/fd/' + str(fd)], (fd,))
    finally: os.close(fd)
    state = json.loads(run('show-state', ['show', '-json']))
    if state['values']['outputs']['proof']['value'] != 'approved-sealed-plan': raise AssertionError('Applied bytes differ from approved snapshot')
    write_json(args.receipt, {'status': 'passed-native-sealed-plan', 'evidence_kind': 'native_opentofu_local_outputs',
        'production_qualified': False, 'provider_rpc_qualified': False, 'live_service_calls': 0,
        'tofu_sha256': pe.PRODUCTION_PINS.tofu_sha256, 'harness_sha256': pe._sha(Path(__file__)),
        'adapter_sha256': pe._sha(Path(pe.__file__)), 'approved_binary_plan_sha256': approved,
        'checks': protected, 'observed_output': 'approved-sealed-plan', 'commands': commands})
    print(json.dumps({'status': 'passed-native-sealed-plan', 'commands': len(commands), 'provider_rpc_qualified': False}))

if __name__ == '__main__': main()
