"""Reuse an existing approved sign-in: detect it through the CLI's own listing, and hand a short-lived read token to one child.

Only documented CLI commands run, with an argument list (never a shell), a deadline, no stdin and a scrubbed environment
that carries no token variable. No credential cache or file is read here, and no token is ever printed, logged or put in an
argument. Detection uses `az account list --output json` and `gh auth status --json hosts`; neither prints a token (the
parsers read an allow-list of fields and ignore the rest). Facts and judgements live in signin_facts (pure); this module
holds the processes.

Environment: the child gets only the variables in ENVIRONMENT_ALLOWED that the parent has (the search path, the home
directory the CLI keeps its own state under, locale, and the CLI's own config-directory variables). Token variables such as
GH_TOKEN, GITHUB_TOKEN, AZURE_CLIENT_SECRET and INTUNE_GRAPH_TOKEN are never forwarded, so a detection never uses, or reports
on, a token that sits in the environment.

Every process runs through _bounded: output is read incrementally under one combined ceiling, and a process that passes the
ceiling or its deadline is killed (with its process group) and reaped before the error is raised. The parent never blocks on
end-of-file: after the kill it waits CLEANUP_GRACE for the pipes to close, and if a writer still holds one (a descendant that
left the session with setsid) it refuses the run as cleanup_unconfirmed.

Limit: the product's own supervised spawn (protected._supervise and its procfs census, protected._cleanup_process_group) was
examined and not reused. It denies network access to its child and is bound to the protected-approval model, and its own
docstring says it is cooperative process-group cleanup, not host containment, so a setsid descendant escapes its census as
well. Here, a descendant that left the session AND closed every inherited pipe cannot be detected by this parent; only a Linux
cgroup (or a subreaper) could contain it, and no such mechanism exists in the product to reuse.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time

from . import signin_facts
from .signin_facts import TENANT_PLACEHOLDER
from .io import AppError

OUTPUT_LIMIT = 256 * 1024
COLLECT_OUTPUT_LIMIT = 256 * 1024
DEFAULT_DEADLINE = 15.0
MAX_TOKEN_LIFETIME = 7200  # seconds a token may still live when it is received; a longer one is not "short-lived"
ENVIRONMENT_ALLOWED = ('PATH', 'HOME', 'USERPROFILE', 'LANG', 'LC_ALL', 'SYSTEMROOT', 'TMPDIR', 'XDG_CONFIG_HOME',
                       'AZURE_CONFIG_DIR', 'GH_CONFIG_DIR', 'AZURE_CORE_COLLECT_TELEMETRY', 'AZURE_CORE_NO_COLOR',
                       'GH_PROMPT_DISABLED', 'NO_COLOR')
_FIXED = {'AZURE_CORE_NO_COLOR': 'true', 'AZURE_CORE_COLLECT_TELEMETRY': 'false', 'GH_PROMPT_DISABLED': '1', 'NO_COLOR': '1'}


def _wall():
    """Wall time, used once, at receipt, to turn the service's own expiry into a remaining lifetime."""
    return time.time()


def _mono():
    """Monotonic time: every later decision about the token's life uses this clock, never the wall clock."""
    return time.monotonic()


class CliError(Exception):
    """A refused or failed CLI call; the code is the whole message (never CLI output)."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def scrubbed_environment():
    environment = {name: os.environ[name] for name in ENVIRONMENT_ALLOWED if name in os.environ}
    environment.update(_FIXED)
    return environment


def _kill(process):
    """Kill the process and its group, then reap it, so nothing is left running or defunct."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        process.kill()
    except OSError:
        pass
    process.wait()


def _bounded(argv, deadline, limit, pass_fds=()):
    """Run argv; returns (exit code, stdout bytes, stderr bytes). Raises CliError: deadline, output_too_large, cli_not_runnable.

    stdout and stderr are read incrementally under one combined ceiling that is enforced while the process runs; on the
    ceiling or the deadline the process is killed and reaped before the error is raised.
    """
    try:
        process = subprocess.Popen(list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=scrubbed_environment(), close_fds=True, pass_fds=tuple(pass_fds), shell=False,
                                   start_new_session=True)
    except OSError:
        raise CliError('cli_not_runnable') from None
    end = time.monotonic() + deadline
    out_fd, err_fd = process.stdout.fileno(), process.stderr.fileno()
    chunks = {out_fd: [], err_fd: []}
    total = 0
    selector = selectors.DefaultSelector()
    try:
        for stream in (process.stdout, process.stderr):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ)
        while selector.get_map():
            remaining = end - time.monotonic()
            if remaining <= 0:
                raise CliError('deadline')
            for key, _ in selector.select(min(remaining, 0.2)):
                try:
                    data = os.read(key.fd, 65536)
                except BlockingIOError:
                    continue
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                total += len(data)
                if total > limit:
                    raise CliError('output_too_large')
                chunks[key.fd].append(data)
        try:
            code = process.wait(timeout=max(end - time.monotonic(), 0.05))
        except subprocess.TimeoutExpired:
            raise CliError('deadline') from None
    except BaseException as error:
        _kill(process)
        if isinstance(error, CliError) and not _streams_closed(selector):
            # Something outside the killed group still holds a pipe open (for example a descendant that left the session).
            # The parent stops reading and never blocks on end-of-file, but it cannot say the run is cleaned up.
            raise CliError('cleanup_unconfirmed') from None
        raise
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()
    return code, b''.join(chunks[out_fd]), b''.join(chunks[err_fd])


CLEANUP_GRACE = 0.5  # seconds after the kill in which every pipe must reach end-of-file


def _streams_closed(selector):
    """After the kill: True when every pipe reached end-of-file within CLEANUP_GRACE (so no writer is left holding one).

    A descendant that closed its pipes and left the session cannot be seen this way; see the limit in the module notes.
    """
    end = time.monotonic() + CLEANUP_GRACE
    while selector.get_map():
        remaining = end - time.monotonic()
        if remaining <= 0:
            return False
        for key, _ in selector.select(min(remaining, 0.05)):
            try:
                data = os.read(key.fd, 65536)  # discarded: only end-of-file matters now
            except BlockingIOError:
                continue
            except OSError:
                data = b''
            if not data:
                selector.unregister(key.fileobj)
    return True


def _run(argv, deadline):
    """Run one documented CLI command; returns (exit code, stdout text, stderr text). Raises CliError with a code."""
    executable = shutil.which(argv[0])
    if executable is None:
        raise CliError('cli_not_found')
    code, out, err = _bounded([executable] + list(argv[1:]), deadline, OUTPUT_LIMIT)
    try:
        return code, out.decode('utf-8'), err.decode('utf-8', 'replace')
    except UnicodeDecodeError:
        raise CliError('malformed_answer') from None


def _unknown(provider, code):
    return {'provider': provider, 'state': 'unknown', 'reason': code, 'accounts': []}


def detect_azure(deadline=DEFAULT_DEADLINE):
    """Azure facts from the CLI's own account listing: tenant, account, cloud and the state word it prints for each entry."""
    try:
        code, out, _ = _run(['az', 'account', 'list', '--output', 'json'], deadline)
    except CliError as error:
        return _unknown('azure', error.code)
    if code != 0:
        return _unknown('azure', 'command_failed')
    return signin_facts.parse_azure(out)


def detect_github(deadline=DEFAULT_DEADLINE):
    """GitHub facts from the CLI's own status: host, account and the state word gh reports for its check of each login."""
    try:
        code, out, err = _run(['gh', 'auth', 'status', '--json', 'hosts'], deadline)
    except CliError as error:
        return _unknown('github', error.code)
    return signin_facts.parse_github(out, code, err)


def detect(which, deadline=DEFAULT_DEADLINE):
    """Facts for 'azure', 'github' or 'all', keyed by provider; only the listings of the chosen providers run."""
    facts = {}
    if which in ('azure', 'all'):
        facts['azure'] = detect_azure(deadline)
    if which in ('github', 'all'):
        facts['github'] = detect_github(deadline)
    return facts


# Judgement and token ---------------------------------------------------------------------------------------------

LISTING_COMMANDS = {'azure': 'az account list --output json', 'github': 'gh auth status --json hosts'}
GRAPH_RESOURCE = 'https://graph.microsoft.com'
TOKEN_LIMIT = 4096  # the descriptor route reads at most this many bytes
_TOKEN_SHAPE = re.compile(r'[A-Za-z0-9._~+/=-]{20,%d}' % TOKEN_LIMIT)
_EXPIRY_TEXT = re.compile(r'[0-9]{9,11}')
_EXPIRED_MARKERS = ('aadsts70043', 'aadsts700082', 'aadsts50173', 'expired', 'interactive authentication is needed')
_NOT_SIGNED_IN_MARKERS = ('az login', 'no subscription', 'not logged in')


class SigninBlocked(Exception):
    """The sign-in cannot be used: the verdict (signin_facts.evaluate or refused) holds both facts and the exact next step."""

    def __init__(self, verdict):
        self.verdict = verdict
        super().__init__(verdict['message'])


class Token(str):
    """A token string that also carries its monotonic deadline: delivery is allowed only before valid_until (see _mono)."""

    valid_until = 0.0

    def __new__(cls, value, valid_until):
        instance = super().__new__(cls, value)
        instance.valid_until = valid_until
        return instance


def status_report(tenant=None, account=None, providers='azure', deadline=DEFAULT_DEADLINE):
    """The facts, the verdict and the commands run for `signin status`; the product runs no sign-in step.

    ready only when Azure is checked and usable in the context tenant and every other requested provider is signed in;
    reported when everything requested is signed in but no tenant comparison could make it ready; otherwise blocked. A ready
    report says once, in ready_for, what it is ready for.
    """
    facts = detect(providers, deadline)
    verdicts = {name: signin_facts.evaluate(value, tenant, account if name == 'azure' else None) for name, value in facts.items()}
    azure = verdicts.get('azure')
    everything = bool(verdicts) and all(v['status'] == 'signed_in' for v in verdicts.values())
    if everything and azure is not None and azure['usable']:
        status = 'ready'
    elif everything:
        status = 'reported'
    else:
        status = 'blocked'
    # The account argument is compared, never echoed: only whether one was given is reported.
    report = {'status': status, 'tenant': tenant, 'account_given': account is not None, **verdicts,
              'commands_run': {name: LISTING_COMMANDS[name] for name in verdicts}}
    if status == 'ready':
        # ready_for is the one place that says Graph, Intune and state-storage access are not known.
        report['ready_for'] = _ready_for(azure['tenant_wanted'], 'github' in verdicts)
    else:
        report['access'] = {'graph': 'unknown', 'intune': 'unknown', 'state_storage': 'unknown'}
        report['note'] = ('A signed-in account does not establish Graph, Intune or state-storage access; those stay unknown until '
                          'a read actually succeeds.')
    return report


def _ready_for(tenant, github):
    """What a ready report is ready for, said once: the Azure CLI sign-in is usable for the tenant, and no access is known."""
    return ('The Azure CLI sign-in is usable for tenant %s%s; Graph, Intune and state-storage access are not known until a '
            'read is attempted.' % (tenant, ' and the GitHub CLI is signed in' if github else ''))


def obtain_token(tenant, account=None, deadline=DEFAULT_DEADLINE):
    """A short-lived Graph read token for the context's tenant through the Azure CLI, after the listing says it is usable.

    The listing runs first; an expired, wrong-tenant or ambiguous sign-in raises SigninBlocked and no token command starts.
    The answer must carry the requested tenant as a GUID and the machine-readable expiry (expires_on, epoch seconds); the
    remaining lifetime must be greater than zero and at most MAX_TOKEN_LIFETIME. A monotonic deadline is armed at receipt
    (Token.valid_until), so a later wall-clock step back never extends the lifetime. The token is returned to the caller and
    goes nowhere else here. The CLI's own error text is never copied into an error or a verdict.
    """
    if signin_facts.shown(tenant, signin_facts.GUID) is None:
        raise AppError('signin_tenant_invalid', 'The tenant must be a GUID.')
    verdict = signin_facts.evaluate(detect_azure(deadline), tenant, account)
    if not verdict['usable']:
        raise SigninBlocked(verdict)
    try:
        code, out, err = _run(['az', 'account', 'get-access-token', '--resource', GRAPH_RESOURCE, '--tenant', tenant,
                               '--output', 'json'], deadline)
    except CliError as error:
        if error.code == 'cleanup_unconfirmed':
            raise AppError('signin_cleanup_unconfirmed', 'The Azure CLI left a process running that could not be confirmed '
                           'gone, so its answer is refused.') from None
        raise AppError('signin_token_deadline' if error.code == 'deadline' else 'signin_token_unavailable',
                       'The Azure CLI did not return a token in time.' if error.code == 'deadline'
                       else 'The Azure CLI could not return a token.') from None
    if code != 0:
        lowered = err.lower()
        if any(marker in lowered for marker in _EXPIRED_MARKERS):
            raise SigninBlocked(signin_facts.refused('expired', tenant))
        if any(marker in lowered for marker in _NOT_SIGNED_IN_MARKERS):
            raise SigninBlocked(signin_facts.refused('not_signed_in', tenant))
        raise AppError('signin_token_unavailable', 'The Azure CLI could not return a token.')
    return _token_from(out, tenant)


def _expires_on(value):
    """Epoch seconds from the machine-readable field, or None; the local-time expiresOn string is never read."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str) and _EXPIRY_TEXT.fullmatch(value):
        return float(value)
    return None


def _token_from(text, tenant):
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        value = None
    token = value.get('accessToken') if isinstance(value, dict) else None
    if not isinstance(token, str) or not _TOKEN_SHAPE.fullmatch(token):
        raise AppError('signin_token_malformed', 'The Azure CLI answer did not hold a usable token.')
    answered = value.get('tenant')
    if not isinstance(answered, str) or not signin_facts.GUID.fullmatch(answered):
        raise AppError('signin_token_malformed', 'The Azure CLI answer did not name the token\'s tenant.')
    if answered.lower() != tenant.lower():
        raise SigninBlocked(signin_facts.refused('wrong_tenant', tenant, answered))
    expires_on = _expires_on(value.get('expires_on'))
    if expires_on is None:
        raise AppError('signin_token_malformed', 'The Azure CLI answer did not carry a usable expiry.')
    remaining = expires_on - _wall()
    if remaining <= 0:
        raise SigninBlocked(signin_facts.refused('expired', tenant))
    if remaining > MAX_TOKEN_LIFETIME:
        raise AppError('signin_token_lifetime_invalid', 'The token lives longer than a short-lived read token may.')
    return Token(token, _mono() + remaining)


# Delivery --------------------------------------------------------------------------------------------------------

COLLECT_DEADLINE = 120.0
_SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'intune-iac.py'
_PATH_FIELDS = ('output', 'export', 'context', 'receipt')
COUNT_BOUND = 100_000
FRAGMENT = 8
# Closed enums: the exact values the capture command can produce. A child-supplied string outside them is never relayed.
COLLECTOR_STATUS = frozenset({'captured', 'partial'})  # capture.py:464
COLLECTOR_KINDS = frozenset({'policies', 'settings', 'assignments'})  # capture.py:349-351
COLLECTOR_COVERAGE = frozenset({'complete', 'partial', 'access_denied'})  # capture.py:352, 381, 418
COLLECTOR_REASONS = frozenset({  # capture.py: limit() 121-129 (cancelled, page_limit, byte_limit, time_limit and auth_stop), read()
    # 151-214 (transport_failed, invalid_transport_response, retry_exhausted, retry_delay_limit, progress_failed), 358-422; the
    # two auth_stop codes come from target.classify_denial (target.py:215, 217).
    'cancelled', 'page_limit', 'byte_limit', 'time_limit', 'token_expired', 'token_wrong_tenant', 'transport_failed',
    'invalid_transport_response', 'retry_exhausted', 'retry_delay_limit', 'progress_failed', 'untrusted_continuation',
    'duplicate_or_looped_page', 'access_denied', 'http_error', 'malformed_json', 'error_envelope', 'invalid_collection_body',
    'invalid_collection_count', 'missing_record_identity', 'duplicate_record_identity', 'invalid_continuation',
    'collection_count_mismatch', 'selected_policy_missing'})
_CREDENTIAL_CODES = frozenset({'token_wrong_tenant', 'token_expired'})


def collector_command(tenant, policy, output, descriptor):
    """The collecting child: the product's own capture command, reading its token from the inherited descriptor."""
    return [sys.executable, '-B', str(_SCRIPT), 'capture', '--tenant', tenant, '--policy', policy, '--output', output,
            '--token-fd', str(descriptor)]


class _Watch:
    """Recognises the token in text without holding it: digests of every FRAGMENT-character window of it.

    The windows are taken from the lower-cased token and from its hex encoding, and text is lower-cased before it is
    compared, so a case change or a hex encoding of the token does not get past it. This is the second line of defence:
    the first is that no child-supplied string outside a closed enum is ever relayed.
    """

    def __init__(self, token):
        lowered = token.lower()
        forms = (lowered, token.encode('utf-8').hex())
        self.digests = {hashlib.sha256(form[i:i + FRAGMENT].encode()).digest()
                        for form in forms for i in range(max(len(form) - FRAGMENT + 1, 1))}
        self.full_digest, self.full_length = hashlib.sha256(token.encode('utf-8')).digest(), len(token.encode('utf-8'))

    def full_match(self, text):
        """True only when the whole delivered token appears, exactly (same case, same characters), in the text."""
        data = text.encode('utf-8', 'replace')
        return any(hmac.compare_digest(hashlib.sha256(data[i:i + self.full_length]).digest(), self.full_digest)
                   for i in range(max(len(data) - self.full_length + 1, 0)))

    def hit(self, text):
        data = text.lower().encode('utf-8', 'replace')
        return any(hashlib.sha256(data[i:i + FRAGMENT]).digest() in self.digests for i in range(max(len(data) - FRAGMENT + 1, 0)))


def _strings(value, found, depth=0):
    """Every decoded string (keys included) in a parsed document; False when the document is too deep or too large."""
    if depth > 12 or len(found) > 4000:
        return False
    if isinstance(value, str):
        found.append(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not _strings(key, found, depth + 1) or not _strings(item, found, depth + 1):
                return False
    elif isinstance(value, list):
        return all(_strings(item, found, depth + 1) for item in value)
    return True


def _count(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= COUNT_BOUND


def collector_schema(value):
    """The only fields of a successful capture result the product shows, or None when the result is outside the schema.

    status, three counts, cancelled and the coverage list (kind, coverage, reason), each of the strings a member of a closed
    enum. A credential problem is reduced to one of two codes. No other field of the child's output is ever relayed, and a
    string outside an enum makes the whole result invalid.
    """
    status = value.get('status') if isinstance(value, dict) else None
    if not isinstance(status, str) or status not in COLLECTOR_STATUS or value.get('cancelled') not in (True, False):
        return None
    if not all(_count(value.get(name)) for name in ('page_count', 'attempt_count', 'retry_count')):
        return None
    coverage = value.get('coverage')
    if not isinstance(coverage, list) or len(coverage) > 16:
        return None
    shown = []
    for item in coverage:
        if not isinstance(item, dict):
            return None
        kind, state, reason = item.get('kind'), item.get('coverage'), item.get('reason')
        if not (isinstance(kind, str) and kind in COLLECTOR_KINDS and isinstance(state, str) and state in COLLECTOR_COVERAGE
                and (reason is None or (isinstance(reason, str) and reason in COLLECTOR_REASONS))):
            return None
        shown.append({'kind': kind, 'coverage': state, 'reason': reason})
    result = {'status': value['status'], 'page_count': value['page_count'], 'attempt_count': value['attempt_count'],
              'retry_count': value['retry_count'], 'cancelled': value['cancelled'], 'coverage': shown}
    problem = value.get('credential_problem')
    if problem is not None:
        # Present means it must be exactly one of the two known codes; anything else invalidates the whole result, so a
        # credential failure can never be quietly omitted.
        code = problem.get('code') if isinstance(problem, dict) else None
        if not isinstance(code, str) or code not in _CREDENTIAL_CODES:
            return None
        result['credential_problem'] = code
    return result


def collect(tenant, policy, output, account=None, deadline=DEFAULT_DEADLINE, collect_deadline=COLLECT_DEADLINE):
    """Collect with the reused sign-in: obtain a short-lived read token and hand it to the one collecting child.

    Order: the listing judges the sign-in (a block ends the call with no token command and no child); the token is obtained;
    a pipe is created and the command built; delivery is refused when the monotonic deadline armed at receipt has passed;
    the token is written to the pipe, its write end closed and the parent's references to it dropped; the child is started
    with the read end as its only extra descriptor (pass_fds), a scrubbed environment and no stdin; the parent closes the read
    end at once. The token is never an argument, never in either environment, never written to a file, and never printed.
    The child's output is read under a ceiling, parsed against a strict schema and checked for the token (decoded, split or
    fragmented) before anything of it is shown.
    """
    if signin_facts.shown(policy, signin_facts.GUID) is None:
        raise AppError('signin_policy_invalid', 'The policy must be a GUID.')
    if not isinstance(output, str) or not output or '\x00' in output:
        raise AppError('signin_output_invalid', 'The output path is not valid.')
    try:
        token = obtain_token(tenant, account, deadline)
    except SigninBlocked as blocked:
        return {'status': 'blocked', 'signin': blocked.verdict, 'collector_started': False}
    watch = _Watch(token)
    # Looked at once before the child starts, only so a withheld result can report what was observed (present before and after);
    # nothing here creates, changes or removes the path, and nothing is inferred from the two observations.
    existed = os.path.lexists(output)
    read_end, write_end = os.pipe()
    try:
        try:
            argv = collector_command(tenant, policy, output, read_end)
            if _mono() >= token.valid_until:
                raise AppError('signin_token_expired', 'The token expired before it could be delivered; nothing was started.')
            os.write(write_end, token.encode('ascii'))  # at most TOKEN_LIMIT bytes: fits the pipe buffer, never blocks
        finally:
            os.close(write_end)
            token = None  # the parent keeps no further reference to the token
        try:
            code, out, err = _bounded(argv, collect_deadline, COLLECT_OUTPUT_LIMIT, pass_fds=(read_end,))
        except CliError as error:
            if error.code == 'cleanup_unconfirmed':
                # A descendant outside the killed group still holds a pipe: nothing the collector produced is trusted.
                return {'status': 'failed', 'error_code': 'cleanup_unconfirmed', 'collector_started': True, 'child_exit': None}
            if error.code == 'output_too_large':
                return {'status': 'failed', 'error_code': 'collector_output_too_large', 'collector_started': True, 'child_exit': None}
            if error.code == 'deadline':
                raise AppError('signin_collect_deadline', 'The collecting command did not finish in time and was stopped.') from None
            raise AppError('signin_collect_unavailable', 'The collecting command could not be started.') from None
    finally:
        os.close(read_end)
    rerun = 'intune-iac signin collect --tenant %s --policy %s --output NEW_DIR (a folder that does not exist yet)%s' % (
        tenant, policy, ' --account NAME (the account you named)' if account is not None else '')
    return _collector_result(code, out, err, watch, output,
                             lambda child_exit, exact: _withheld(child_exit, output, existed, rerun, exact), rerun, tenant)


def _observe(output):
    """What is at the output path now, observed once and not interpreted: absent, symlink, directory or other."""
    if not os.path.lexists(output):
        return 'absent'
    if os.path.islink(output):
        return 'symlink'
    return 'directory' if os.path.isdir(output) else 'other'


def _withheld(code, output, before, rerun, exact):
    """The output contained the token or credential-shaped text: nothing of it is shown. Report only what was observed.

    The output path is looked at before the child starts and again now; those two observations do not show which process
    created, changed or removed anything, so no creation, removal or ownership is claimed and no deletion command is printed.
    The access token is named only when the whole delivered token matched exactly, in raw stdout, raw stderr or one decoded
    string; never in a concatenation of fragments.
    """
    kind = _observe(output)
    after = kind != 'absent'
    detail = {'absent': '', 'symlink': ' (it is a symbolic link)', 'directory': ' (it is a directory)',
              'other': ' (it is not a directory)'}[kind]
    subject = ('contained the access token itself' if exact else 'contained the token or credential-shaped text')
    return {'status': 'failed', 'error_code': 'collector_output_withheld', 'collector_started': True, 'child_exit': code,
            'token_match': 'full_token' if exact else 'fragment_or_shape',
            'output_present_before': before, 'output_present_after': after, 'output_kind_after': kind,
            'message': 'The output of the collecting command %s and was withheld, so nothing of it is shown. The output path '
                       '%s before this run and %s after it%s. This command cannot determine which process created, changed or removed '
                       'that path.' % (subject, 'was present' if before else 'was not present',
                                                                 'is present' if after else 'is not present', detail),
            'next_step': 'If you need to know what is at the output path, look at it yourself (this command did not open it); '
                         'then run: ' + rerun + '.' + (' The collecting command printed the access token: stop and report it.'
                                                       if exact else '')}


def _invalid(code):
    return {'status': 'failed', 'error_code': 'collector_output_invalid', 'collector_started': True, 'child_exit': code}


def _partial_next_step(output, rerun, tenant, shown):
    """What to do after a partial capture: the folder the run wrote is named (never opened or removed here), then the cause."""
    cause = ''
    problem = shown.get('credential_problem')
    if problem in _CREDENTIAL_CODES:
        cause = ('The service said the token %s; sign in again: az login --tenant %s; then ' % (
            'belongs to a different tenant' if problem == 'token_wrong_tenant' else 'has expired', tenant))
    elif any(item['coverage'] == 'access_denied' for item in shown['coverage']):
        cause = ('The service denied the read; ask your administrator whether the signed-in account may read these Intune objects; '
                 'then ')
    return ('The run wrote the output folder %s (what was captured before it stopped); this command did not open or remove it, '
            'and a new run cannot reuse it. %sTo collect again, run: %s.' % (output, cause, rerun))


def _collector_result(code, out, err, watch, output, withheld, rerun='', tenant=TENANT_PLACEHOLDER):
    """The collecting command's result. Its documented exits are 0 (captured) and 2 (partial); anything else is a failure."""
    text_out, text_err = out.decode('utf-8', 'replace'), err.decode('utf-8', 'replace')
    if watch.hit(text_out) or watch.hit(text_err):
        return withheld(code, watch.full_match(text_out) or watch.full_match(text_err))
    if code not in (0, 2):
        return {'status': 'failed', 'error_code': _error_code(text_err), 'collector_started': True, 'child_exit': code}
    try:
        value = json.loads(text_out)
    except (ValueError, RecursionError):
        return _invalid(code)
    found = []
    if not _strings(value, found):
        return _invalid(code)
    # Decoded strings (JSON escapes undone), one by one and joined, so a token split over fields is still recognised.
    if watch.hit(''.join(found)) or any(watch.hit(item) for item in found):
        # Fragments only found in the concatenation never count as the whole token: only one decoded string can.
        return withheld(code, any(watch.full_match(item) for item in found))
    for key, item in (value.items() if isinstance(value, dict) else ()):
        if key not in _PATH_FIELDS and isinstance(item, str) and _TOKEN_SHAPE.fullmatch(item):
            return withheld(code, False)  # shaped like a credential; not shown to be the delivered token
    shown = collector_schema(value)
    # The status and the exit code must agree: exit 0 is captured, exit 2 is partial.
    if shown is None or shown['status'] != ('captured' if code == 0 else 'partial'):
        return _invalid(code)
    if code == 0:
        return {'status': 'collected', 'collector_started': True, 'child_exit': 0, 'result': dict(shown, output=output)}
    return {'status': 'partial', 'collector_started': True, 'child_exit': 2, 'result': dict(shown, output=output),
            'next_step': _partial_next_step(output, rerun, tenant, shown)}


def _error_code(text):
    """The error code on the child's last JSON line of stderr when it is a plain code; never any other text."""
    for line in reversed(text.splitlines()):
        try:
            value = json.loads(line)
        except (ValueError, RecursionError):
            continue
        error = value.get('error') if isinstance(value, dict) else None
        code = error.get('code') if isinstance(error, dict) else None
        return signin_facts.shown_code(code) or 'collector_failed'
    return 'collector_failed'
