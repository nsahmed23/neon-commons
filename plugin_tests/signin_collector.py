"""A stand-in for the collecting child (intune-iac capture --token-fd N), used by the sign-in delivery tests.

It reads the token the way the real child does (provider_journey.read_token_fd, the descriptor route), checks that the token
is nowhere else in its own process (argument list, environment), and writes only the SHA-256 and length of what it received
to the file named by --report (when given). On stdout it prints a result shaped like capture's, so the parent's strict
result schema is exercised. Modes (--mode) make it misbehave: escaped, split, echo, extra, fail, sleep, flood.
It never prints, logs or writes the token, except in the deliberate leaking modes. Run it with
`python -I collector.py ROOT --token-fd N [--mode MODE] [--report PATH]`.
"""
import hashlib
import json
import os
import sys


def result(**more):
    value = {'status': 'captured', 'output': '/somewhere/out', 'export': '/somewhere/out/export.json',
             'context': '/somewhere/out/context.json', 'receipt': '/somewhere/out/capture-receipt.json', 'page_count': 3,
             'attempt_count': 3, 'retry_count': 0, 'cancelled': False,
             'coverage': [{'kind': 'policies', 'coverage': 'complete', 'reason': None}],
             'tenant_assurance': 'caller_asserted', 'source_authenticity_verified': False, 'provider_qualified': False,
             'execution_authorized': False}
    value.update(more)
    return value


def main(argv):
    root, rest = argv[0], argv[1:]
    sys.path.insert(0, root)
    from intune_iac.provider_journey import read_token_fd
    descriptor = int(rest[rest.index('--token-fd') + 1])
    mode = rest[rest.index('--mode') + 1] if '--mode' in rest else 'ok'
    token = read_token_fd(descriptor)
    if '--report' in rest:
        report = {'received_sha256': hashlib.sha256(token.encode()).hexdigest(), 'length': len(token),
                  'token_in_environment': any(token in value for value in os.environ.values()),
                  'token_in_arguments': any(token in item for item in sys.argv), 'argument_count': len(sys.argv)}
        with open(rest[rest.index('--report') + 1], 'w') as handle:
            json.dump(report, handle)
    if mode == 'fail':
        print(json.dumps({'status': 'error', 'error': {'code': 'collector_failed', 'message': 'x'}}), file=sys.stderr)
        return 3
    if mode == 'failcode':
        print(json.dumps({'status': 'error', 'error': {'code': rest[rest.index('--code') + 1]}}), file=sys.stderr)
        return 3
    if mode == 'sleep':
        import time
        time.sleep(30)
    if mode == 'flood':
        while True:
            sys.stdout.write('x' * 65536)
            sys.stdout.flush()
    if mode == 'lowercase':
        print(json.dumps(result(coverage=[{'kind': token.lower(), 'coverage': 'complete', 'reason': None}])))
    elif mode == 'hexsplit':
        digits = token.encode().hex()
        half = len(digits) // 2
        print(json.dumps(result(coverage=[{'kind': 'h' + digits[:half], 'coverage': 'complete', 'reason': 'h' + digits[half:]}])))
    elif mode in ('deep', 'deep1500'):
        depth = 1500 if mode == 'deep1500' else 100000  # 1,500 parses on this Python; 100,000 raises RecursionError
        print('[' * depth + ']' * depth)
    elif mode == 'escape':
        # A grandchild that leaves the session and group, keeps this process's stdout open, and sleeps.
        import subprocess
        import time
        code = 'import os, time; os.setsid(); open(%r, "w").write(str(os.getpid())); time.sleep(60)' % rest[rest.index('--pidfile') + 1]
        subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.DEVNULL)
        time.sleep(0.5)
        print(json.dumps(result()))
    elif mode == 'echo':
        print(json.dumps(result(echo=token)))
    elif mode == 'escaped':
        print(json.dumps(result(leak=token)).replace('/', '\\/'))
    elif mode == 'split':
        half = len(token) // 2
        print(json.dumps(result(alpha=token[:half], beta=token[half:])))
    elif mode == 'rawecho':
        print(token)
    elif mode == 'nestedhalves':
        half = len(token) // 2
        print(json.dumps(result(note=[token[:half], token[half:]])))  # halves in one ignored nested list
    elif mode == 'shapednote':
        print(json.dumps(result(note='abcdefghijklmnopqrst')))  # credential-shaped text that is NOT the delivered token
    elif mode in ('partial_expired', 'partial_denied'):
        # capture exits 2 with status partial; an expired token adds the credential problem (the product relays closed codes only)
        expired = mode == 'partial_expired'
        coverage = [{'kind': 'policies', 'coverage': 'complete', 'reason': None},
                    {'kind': 'settings', 'coverage': 'partial' if expired else 'access_denied',
                     'reason': 'token_expired' if expired else 'access_denied'}]
        more = {'credential_problem': {'code': 'token_expired'}} if expired else {}
        print(json.dumps(result(status='partial', coverage=coverage, **more)))
        return 2
    elif mode == 'extra':
        print(json.dumps(result(note='a field the product does not show', nested={'deep': 'value'})))
    else:
        print(json.dumps(result()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
