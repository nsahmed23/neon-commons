#!/usr/bin/env python3
"""Run the documented local journey and retain auditable synthetic evidence."""
from pathlib import Path
import argparse
import json
import subprocess
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from intune_iac.io import AppError, file_sha, load_json, write_json
from intune_iac.journey import run_journey, reconstruct_progress, STAGES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='Fresh local directory for fixture and journey evidence.')
    parser.add_argument('--cli', action='store_true', help='Exercise the actual wizard CLI from the output directory.')
    parser.add_argument('--snapshot', help='Optional fresh directory for a compact record-only evidence snapshot.')
    args = parser.parse_args()
    implementation_paths = ['intune_iac/journey.py', 'intune_iac/workflow.py', 'intune_iac/engine.py',
                            'intune_iac/protected.py', 'intune_iac/modeled_service.py',
                            'intune_iac/cli.py', 'scripts/qualify-journey.py']
    implementation_hashes = {name: file_sha(ROOT / name) for name in implementation_paths}
    output = Path(args.output).absolute()
    if output.exists():
        parser.error('Output must be fresh; previous evidence is preserved.')
    output.mkdir(parents=True, mode=0o700)
    source = output / 'capture.json'; context = output / 'context.json'
    source.write_bytes((ROOT / 'examples/supported/input/export.json').read_bytes())
    context.write_bytes((ROOT / 'examples/context.json').read_bytes())
    policy = load_json(context)['selected_policy_id']
    answers = ['continue'] * 3 + [policy] + ['continue'] * 4 + ['generate', 'continue', 'continue', 'plan', 'approve', 'execute', 'reconcile', 'continue', 'finish']
    queue = iter(answers); transcript = []
    def read(prompt):
        value = next(queue, None)
        if value is None: raise EOFError()
        transcript.append({'prompt': prompt, 'answer': value})
        return value
    session = output / 'session.json'
    cli_exit = None
    if args.cli:
        command = [sys.executable, str(ROOT / 'scripts/intune-iac.py'), 'wizard', '--journey',
                   '--session', str(session), '--input', str(source), '--context', str(context),
                   '--output', str(output / 'proposals'), '--journey-mode', 'simulation']
        process = subprocess.run(command, input='\n'.join(answers) + '\n', text=True,
                                 capture_output=True, cwd=output, timeout=240)
        (output / 'cli.stdout.txt').write_text(process.stdout)
        (output / 'cli.stderr.txt').write_text(process.stderr)
        cli_exit = process.returncode
        transcript = [{'command': command, 'answers': answers, 'exit_code': cli_exit}]
        result = {'status': load_json(session)['lifecycle'] if session.is_file() else 'session_not_created', 'cli_exit_code': cli_exit}
    else:
        result = run_journey(session, source, context, output / 'proposals', input_fn=read,
                             output_fn=lambda message: transcript.append({'message': message}), mode='simulation')
    try:
        progress = reconstruct_progress(session)
    except (AppError, OSError, ValueError, ImportError) as error:
        # A failed prerequisite/CLI attempt still receives a durable negative
        # receipt. Do not crash while trying to reconstruct a missing session.
        progress = {'verified_completed': [], 'live_ready': False,
                    'live_blockers': ['journey_reconstruction_unavailable'],
                    'execution_authorized': False, 'external_verified_completed': [],
                    'error': getattr(error, 'code', type(error).__name__)}
    checks = {'completed_all_stages': result.get('status') == 'complete_simulation' and progress['verified_completed'] == list(STAGES),
              'implementation_unchanged': implementation_hashes == {name: file_sha(ROOT / name) for name in implementation_paths},
              'live_gates_retained': not progress['live_ready'] and bool(progress['live_blockers']),
              'no_cloud_authority': not progress['execution_authorized'] and progress['external_verified_completed'] == [],
              'generated_current_source': (output / 'proposals' / policy / 'generated-files.json').is_file()}
    if args.cli: checks['actual_cli_succeeded'] = cli_exit == 0
    report = {'schema_version': 'journey-qualification/1.0', 'scope': 'Actual CLI/local engine generation, full semantic model state and bounded synthetic child process, with independent raw-capture projection and modeled service GET readback; no native provider/Atmos or cloud execution.',
              'success': all(checks.values()), 'checks': checks, 'stages': list(STAGES),
              'implementation_sha256': implementation_hashes,
              'dependency_lock_sha256': file_sha(ROOT / 'dependency-lock.json'),
              'capture_sha256': file_sha(source), 'action_contract_sha256': file_sha(ROOT / 'contracts/journey-actions.json'),
              'result': result, 'reconstruction': progress}
    write_json(output / 'qualification.json', report)
    write_json(output / 'transcript.json', transcript)
    if args.snapshot and report['success']:
        snapshot = Path(args.snapshot).absolute()
        if snapshot.exists() or snapshot == output or output in snapshot.parents:
            parser.error('Snapshot must be a fresh directory outside the operational output.')
        shutil.copytree(output, snapshot, ignore=shutil.ignore_patterns('tool', '__pycache__'))
        manifest = load_json(output / 'session.json.journey/synthetic-executor/executor.json')
        write_json(snapshot / 'SNAPSHOT.json', {'scope': 'record_only_evidence_snapshot',
                   'operational_source': str(output), 'self_contained_runtime': False,
                   'omitted': ['synthetic-executor/tool', '__pycache__'],
                   'omitted_executable_sha256': manifest['executable_sha256'],
                   'reproduce': 'Run qualify-journey.py with a fresh --output using the installed pinned dependencies.'})
    print(json.dumps({'success': report['success'], 'checks': checks, 'result': str(output / 'qualification.json')}, indent=2))
    return 0 if report['success'] else 1

if __name__ == '__main__': raise SystemExit(main())
