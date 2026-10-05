#!/usr/bin/env python3
"""Exercise real CLI PTY navigation and durable recovery, never cloud execution.

The PTY profile uses process signals to deliver Ctrl-C semantics. Receipts and
transcripts identify these as actual CLI processes; stateful API fault tests are
separate. Output must be fresh. The harness never deletes an existing artifact.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from intune_iac.io import file_sha, load_json, write_json
from intune_iac.journey import reconstruct_progress, STAGES
from intune_iac.synthetic import generate_estate

PROMPT = b']: '

class Terminal:
    def __init__(self, argv, cwd, destination):
        self.destination = destination; self.data = bytearray(); self.pending = bytearray(); self.events = []
        self.master, slave = pty.openpty()
        self.process = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave, cwd=cwd,
                                        close_fds=True, start_new_session=True)
        os.close(slave)
        self.events.append({'event': 'spawn', 'command': argv, 'pid': self.process.pid, 'time': time.time()})
    def prompt(self, timeout=60):
        deadline = time.monotonic() + timeout
        while PROMPT not in self.pending:
            if time.monotonic() >= deadline: raise RuntimeError('PTY prompt deadline exceeded')
            if not select.select([self.master], [], [], .25)[0]:
                if self.process.poll() is not None: raise RuntimeError('CLI exited before next prompt')
                continue
            try: chunk = os.read(self.master, 65536)
            except OSError: chunk = b''
            if not chunk: raise RuntimeError('PTY closed before next prompt')
            self.data.extend(chunk); self.pending.extend(chunk)
        end = self.pending.index(PROMPT) + len(PROMPT)
        seen = bytes(self.pending[:end]); del self.pending[:end]
        self.events.append({'event': 'prompt', 'time': time.time(), 'text': seen.decode(errors='replace')})
        return seen.decode(errors='replace')
    def answer(self, value):
        self.events.append({'event': 'answer', 'text': value, 'time': time.time()})
        os.write(self.master, (value + '\n').encode())
    def interrupt(self):
        self.events.append({'event': 'SIGINT', 'time': time.time()})
        os.kill(self.process.pid, signal.SIGINT)
    def finish(self):
        try:
            deadline = time.monotonic() + 60
            while self.process.poll() is None or select.select([self.master], [], [], 0)[0]:
                if time.monotonic() >= deadline: raise RuntimeError('CLI exit deadline exceeded')
                if select.select([self.master], [], [], .25)[0]:
                    try: chunk = os.read(self.master, 65536)
                    except OSError: break
                    if not chunk: break
                    self.data.extend(chunk)
            code = self.process.wait(timeout=5)
            self.destination.with_suffix('.stdout.txt').write_bytes(self.data)
            write_json(self.destination.with_suffix('.transcript.json'), self.events + [{'event': 'exit', 'code': code}])
            return code
        finally:
            if self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGTERM)
                try: self.process.wait(timeout=3)
                except subprocess.TimeoutExpired: os.killpg(self.process.pid, signal.SIGKILL); self.process.wait()
            # Negative attempts preserve their actual available transcript too.
            self.destination.with_suffix('.stdout.txt').write_bytes(self.data)
            write_json(self.destination.with_suffix('.transcript.json'), self.events + [{'event': 'exit_or_cleanup', 'code': self.process.poll()}])
            os.close(self.master)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(); output = Path(args.output).absolute()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    source = output / 'capture.json'; context = output / 'context.json'
    estate = generate_estate(seed=104, policy_count=3)
    write_json(source, estate['capture']); write_json(context, estate['contexts'][0]); write_json(output / 'truth.json', estate['truth'])
    ids = [p['id'] for p in estate['truth']['policies']]
    session = output / 'session.json'; proposals = output / 'proposals'
    basic = [sys.executable, '-B', str(ROOT / 'scripts/intune-iac.py'), 'wizard', '--journey', '--session', str(session)]
    checks, results = {}, []
    def run(name, answers, first=False, interrupt=False):
        argv = basic + (['--input', str(source), '--context', str(context), '--output', str(proposals), '--journey-mode', 'simulation'] if first else [])
        term = Terminal(argv, output, output / name)
        try:
            for value in answers: term.prompt(); term.answer(value)
            if interrupt: term.prompt(); term.interrupt()
        except BaseException:
            if term.process.poll() is None: os.kill(term.process.pid, signal.SIGINT)
            term.finish(); raise
        code = term.finish(); results.append({'id': name, 'exit_code': code, 'interaction': 'actual_cli_pty'})
        return reconstruct_progress(session)
    before = ['continue'] * 3 + [','.join(ids)] + ['continue'] * 4
    # Navigate back through the actual CLI and then approve; Ctrl-C before execute.
    answers = before[:4] + ['back inventory', 'continue', ','.join(ids)] + ['continue'] * 4 + ['generate', 'continue', 'continue', 'plan', 'approve']
    progress = run('PTY-01-back-and-interrupt', answers, first=True, interrupt=True)
    checks['back_then_interrupt_requires_fresh_approval'] = progress['next_state'] == 'approval' and 'execute' not in progress['verified_completed']
    checks['interrupt_removed_session_lock'] = not list(output.glob('.intune-wizard-lock-*'))
    progress = run('PTY-02-cancel', ['execute', 'cancel'])
    checks['cancel_persists'] = load_json(session)['lifecycle'] == 'cancelled' and 'execute' not in progress['verified_completed']
    progress = run('PTY-03-resume-and-complete', ['execute', 'resume', 'approve', 'execute', 'reconcile', 'continue', 'finish'])
    checks['resume_completed_all_stages'] = progress['verified_completed'] == list(STAGES)
    checks['full_three_policy_semantics'] = sorted(load_json(Path(str(session) + '.journey') / 'modeled-readback.json')['estate']['objects']) == sorted(ids)
    before_hashes = {str(p.relative_to(proposals)): file_sha(p) for p in proposals.rglob('*') if p.is_file()}
    new_output = output / 'edited-proposals'
    progress = run('PTY-04-edit-output-and-revalidate', ['back generation', 'edit output ' + str(new_output), 'generate', 'continue', 'continue', 'plan', 'approve', 'execute', 'reconcile', 'continue', 'finish'])
    checks['edit_completed_all_stages'] = progress['verified_completed'] == list(STAGES)
    checks['existing_artifacts_preserved'] = before_hashes == {str(p.relative_to(proposals)): file_sha(p) for p in proposals.rglob('*') if p.is_file()}
    # Remove only the task-owned input; resume must permit repairing its locator.
    replacement = output / 'replacement.json'; replacement.write_bytes(source.read_bytes()); source.unlink()
    progress = run('PTY-05-repair-missing-source', ['edit input ' + str(replacement), 'save'])
    checks['missing_source_repaired_interactively'] = load_json(session)['paths']['input'] == str(replacement) and progress['next_state'] == 'inventory'
    # Suspended/cancelled exit code is a state, not an execution success claim.
    checks['no_cloud_authority'] = all(not progress[k] for k in ('live_ready', 'execution_authorized'))
    hashes = {str(p.relative_to(ROOT)): file_sha(p) for p in [ROOT / 'intune_iac/journey.py', ROOT / 'intune_iac/modeled_service.py', ROOT / 'scripts/qualify-journey-navigation.py']}
    report = {'schema_version': 'journey-navigation-epoch/1.0', 'scope': 'actual CLI PTY and modeled semantic-service adoption; no native provider, Atmos or live Graph',
        'success': all(checks.values()), 'checks': checks, 'runs': results, 'source_hashes': hashes,
        'selected_ids': ids, 'seed': 104, 'production_qualified': False,
        'replay': [sys.executable, '-B', str(Path(__file__).resolve()), '--output', 'FRESH_DIRECTORY']}
    write_json(output / 'qualification.json', report)
    print(json.dumps({'success': report['success'], 'checks': checks, 'report': str(output / 'qualification.json')}, indent=2))
    return 0 if report['success'] else 1

if __name__ == '__main__': raise SystemExit(main())
