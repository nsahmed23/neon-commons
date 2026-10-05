#!/usr/bin/env python3
"""Actual pinned Atmos comparison inside the full modeled operator journey.

Runs the actual wizard CLI with scripted stdin. Native configuration comparison,
protected local subprocess adoption, synthetic service GETs, and live gates are
asserted independently and retain distinct evidence classes.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from intune_iac.io import digest, file_sha, load_json, write_json
from intune_iac.journey import STAGES, reconstruct_progress


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True); parser.add_argument('--atmos-executable', required=True)
    parser.add_argument('--tofu-executable', help='Also execute the native output-only OpenTofu saved plan and second plan')
    args = parser.parse_args(); out = Path(args.output).absolute(); out.mkdir(mode=0o700, parents=True, exist_ok=False)
    repo = out / 'repository'; (repo / 'stacks').mkdir(parents=True); (repo / 'components/terraform/intune-reference').mkdir(parents=True)
    (repo / 'atmos.yaml').write_text("stacks: {base_path: stacks, included_paths: ['**/*'], name_pattern: '{stage}'}\ncomponents: {terraform: {base_path: components/terraform, command: tofu}}\n")
    (repo / 'stacks/reference-dev.yaml').write_text('vars: {stage: reference-dev, tenant: descriptive-label}\ncomponents: {terraform: {intune-reference: {vars: {value: 1}}}}\n')
    (repo / 'components/terraform/intune-reference/main.tf').write_text('variable "value" { type = number }\n')
    source, context, session = out / 'capture.json', out / 'context.json', out / 'session.json'
    source.write_bytes((ROOT / 'examples/supported/input/export.json').read_bytes())
    context.write_bytes((ROOT / 'examples/context.json').read_bytes())
    policy = load_json(context)['selected_policy_id']
    command = [sys.executable, '-B', str(ROOT / 'scripts/intune-iac.py'), 'wizard', '--journey', '--session', str(session),
        '--input', str(source), '--context', str(context), '--output', str(out / 'proposals'), '--repo', str(repo),
        '--atmos-executable', str(Path(args.atmos_executable).absolute()), '--journey-mode', 'simulation']
    if args.tofu_executable: command.extend(['--tofu-executable', str(Path(args.tofu_executable).absolute())])
    answers = ['continue'] * 3 + [policy] + ['continue'] * 4 + ['generate', 'continue', 'continue', 'plan', 'approve', 'execute', 'reconcile', 'continue', 'finish']
    run = subprocess.run(command, input='\n'.join(answers) + '\n', text=True, capture_output=True, cwd=out, timeout=180)
    (out / 'stdout.txt').write_text(run.stdout); (out / 'stderr.txt').write_text(run.stderr)
    write_json(out / 'invocation.json', {'command': command, 'answers': answers, 'exit_code': run.returncode, 'interaction': 'actual_cli_scripted_stdin'})
    checks = {'cli_succeeded': run.returncode == 0}
    try:
        progress = reconstruct_progress(session)
        receipt = load_json(Path(str(session) + '.journey') / 'receipts/atmos.json')['payload']
        native = load_json(Path(str(session) + '.journey') / 'native-atmos.json')['report']
        expected_vars = {'stage': 'reference-dev', 'tenant': 'descriptive-label', 'value': 1}
        checks.update(all_stages=progress['verified_completed'] == list(STAGES),
            native_tool_executed=receipt['native_atmos_executed'] is True and native['native_executed'] is True,
            independent_vars=native['comparison_sha256']['vars']['observed'] == digest(expected_vars),
            explicit_no_authentication=native['tenant_authenticated'] is False,
            no_cloud_authority=not progress['execution_authorized'] and not progress['live_ready'],
            native_and_model_scopes=receipt['assurance'] == 'native_configuration_only')
        if args.tofu_executable:
            convergence = load_json(Path(str(session) + '.journey') / 'receipts/convergence.json')['payload']
            checks['actual_native_second_plan'] = convergence['scope'] == 'native_local_output_only_and_synthetic_service' and convergence['native_second_plan']['status'] == 'verified'
    except (OSError, KeyError, ValueError) as error:
        checks['evidence_reconstruction'] = False
        progress = {'error': getattr(error, 'code', type(error).__name__)}
    report = {'schema_version': 'connected-native-atmos/1.0', 'success': all(checks.values()), 'checks': checks,
        'scope': 'actual pinned Atmos configuration comparison inside modeled full CLI journey; no native Microsoft365 provider or live Graph mutation',
        'source_hashes': {name: file_sha(ROOT / name) for name in ('intune_iac/journey.py', 'intune_iac/journey_native_atmos.py', 'intune_iac/native_atmos.py', 'scripts/qualify-connected-atmos.py')},
        'reconstruction': progress, 'production_qualified': False}
    write_json(out / 'qualification.json', report)
    print(json.dumps({'success': report['success'], 'checks': checks, 'report': str(out / 'qualification.json')}, indent=2))
    return 0 if report['success'] else 1

if __name__ == '__main__': raise SystemExit(main())
