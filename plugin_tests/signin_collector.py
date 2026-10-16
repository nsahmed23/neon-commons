"""A stand-in for the collecting child (intune-iac capture --token-fd N), used by the sign-in delivery tests.

It reads the token the way the real child does (provider_journey.read_token_fd, the descriptor route), checks that the token
is nowhere else in its own process (argument list, environment), and prints only the SHA-256 and length of what it received.
It never prints, logs or writes the token. Run it with `python -I collector.py ROOT --token-fd N [--mode MODE]`.
"""
import hashlib
import json
import os
import sys


def main(argv):
    root, rest = argv[0], argv[1:]
    sys.path.insert(0, root)
    from intune_iac.provider_journey import read_token_fd
    descriptor = int(rest[rest.index('--token-fd') + 1])
    mode = rest[rest.index('--mode') + 1] if '--mode' in rest else 'ok'
    token = read_token_fd(descriptor)
    elsewhere = [name for name, value in os.environ.items() if token in value]
    in_arguments = any(token in item for item in sys.argv)
    report = {'received_sha256': hashlib.sha256(token.encode()).hexdigest(), 'length': len(token),
              'token_in_environment': bool(elsewhere), 'token_in_arguments': in_arguments,
              'argument_count': len(sys.argv)}
    if mode == 'echo':
        report['echo'] = token  # a misbehaving collector: the parent must withhold this
    if mode == 'fail':
        print(json.dumps({'status': 'error', 'error': {'code': 'collector_failed', 'message': 'x'}}), file=sys.stderr)
        return 3
    if mode == 'sleep':
        import time
        time.sleep(30)
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
