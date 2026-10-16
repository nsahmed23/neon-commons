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
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from . import signin_facts
from .io import AppError

OUTPUT_LIMIT = 256 * 1024
DEFAULT_DEADLINE = 15.0
ENVIRONMENT_ALLOWED = ('PATH', 'HOME', 'USERPROFILE', 'LANG', 'LC_ALL', 'SYSTEMROOT', 'TMPDIR', 'XDG_CONFIG_HOME',
                       'AZURE_CONFIG_DIR', 'GH_CONFIG_DIR', 'AZURE_CORE_COLLECT_TELEMETRY', 'AZURE_CORE_NO_COLOR',
                       'GH_PROMPT_DISABLED', 'NO_COLOR')
_FIXED = {'AZURE_CORE_NO_COLOR': 'true', 'AZURE_CORE_COLLECT_TELEMETRY': 'false', 'GH_PROMPT_DISABLED': '1', 'NO_COLOR': '1'}


class CliError(Exception):
    """A refused or failed CLI call; the code is the whole message (never CLI output)."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def scrubbed_environment():
    environment = {name: os.environ[name] for name in ENVIRONMENT_ALLOWED if name in os.environ}
    environment.update(_FIXED)
    return environment


def _run(argv, deadline):
    """Run one documented CLI command; returns (exit code, stdout text, stderr text). Raises CliError with a code."""
    executable = shutil.which(argv[0])
    if executable is None:
        raise CliError('cli_not_found')
    try:
        done = subprocess.run([executable] + list(argv[1:]), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, env=scrubbed_environment(), timeout=deadline, shell=False,
                              close_fds=True)
    except subprocess.TimeoutExpired:
        raise CliError('deadline') from None
    except OSError:
        raise CliError('cli_not_runnable') from None
    if len(done.stdout) > OUTPUT_LIMIT or len(done.stderr) > OUTPUT_LIMIT:
        raise CliError('output_too_large')
    try:
        return done.returncode, done.stdout.decode('utf-8'), done.stderr.decode('utf-8', 'replace')
    except UnicodeDecodeError:
        raise CliError('malformed_answer') from None


def _unknown(provider, code):
    return {'provider': provider, 'state': 'unknown', 'reason': code, 'accounts': []}


def detect_azure(deadline=DEFAULT_DEADLINE):
    """Azure facts from the CLI's own account listing: tenant, account, cloud and the session state it reports."""
    try:
        code, out, _ = _run(['az', 'account', 'list', '--output', 'json'], deadline)
    except CliError as error:
        return _unknown('azure', error.code)
    if code != 0:
        return _unknown('azure', 'command_failed')
    return signin_facts.parse_azure(out)


def detect(which, deadline=DEFAULT_DEADLINE):
    """Facts for 'azure', 'github' or 'all', keyed by provider; only the listings of the chosen providers run."""
    facts = {}
    if which in ('azure', 'all'):
        facts['azure'] = detect_azure(deadline)
    if which in ('github', 'all'):
        facts['github'] = detect_github(deadline)
    return facts


def detect_github(deadline=DEFAULT_DEADLINE):
    """GitHub facts from the CLI's own status: host, account, whether a session exists."""
    try:
        code, out, err = _run(['gh', 'auth', 'status', '--json', 'hosts'], deadline)
    except CliError as error:
        return _unknown('github', error.code)
    return signin_facts.parse_github(out, code, err)


# Judgement and token ---------------------------------------------------------------------------------------------

LISTING_COMMANDS = {'azure': 'az account list --output json', 'github': 'gh auth status --json hosts'}
GRAPH_RESOURCE ='https://graph.microsoft.com'
TOKEN_LIMIT = 4096  # the descriptor route reads at most this many bytes
_TOKEN_SHAPE = re.compile(r'[A-Za-z0-9._~+/=-]{20,%d}' % TOKEN_LIMIT)
_EXPIRED_MARKERS = ('aadsts70043', 'aadsts700082', 'aadsts50173', 'expired', 'interactive authentication is needed')
_NOT_SIGNED_IN_MARKERS = ("az login", 'no subscription', 'not logged in')


class SigninBlocked(Exception):
    """The sign-in cannot be used: the verdict (signin_facts.evaluate or refused) holds both facts and the exact next step."""

    def __init__(self, verdict):
        self.verdict = verdict
        super().__init__(verdict['message'])


def status_report(tenant=None, account=None, providers='azure', deadline=DEFAULT_DEADLINE):
    """The facts, the verdict and the commands run for `signin status`; the product runs no sign-in step."""
    facts = detect(providers, deadline)
    verdicts = {name: signin_facts.evaluate(value, tenant, account if name == 'azure' else None) for name, value in facts.items()}
    azure = verdicts.get('azure')
    if azure is not None and azure['usable']:
        status = 'ready'
    elif azure is not None and tenant is None and azure['status'] == 'signed_in':
        status = 'reported'
    elif azure is None and verdicts and all(v['status'] == 'signed_in' for v in verdicts.values()):
        status = 'reported'
    else:
        status = 'blocked'
    return {'status': status, 'tenant': tenant, 'account': account, **verdicts,
            'access': {'graph': 'unknown', 'intune': 'unknown', 'state_storage': 'unknown'},
            'note': 'A signed-in account does not establish Graph, Intune or state-storage access; those stay unknown until a '
                    'read actually succeeds.',
            'commands_run': {name: LISTING_COMMANDS[name] for name in verdicts}}


def obtain_token(tenant, account=None, deadline=DEFAULT_DEADLINE):
    """A short-lived Graph read token for the context's tenant through the Azure CLI, after the listing says it is usable.

    The listing runs first; an expired, wrong-tenant or ambiguous sign-in raises SigninBlocked and no token command starts.
    The token is returned to the caller and goes nowhere else here: not printed, logged, put in an argument or the
    environment, or written to a file. The CLI's own error text is never copied into an error or a verdict.
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


def _token_from(text, tenant):
    try:
        value = json.loads(text)
    except ValueError:
        value = None
    token = value.get('accessToken') if isinstance(value, dict) else None
    if not isinstance(token, str) or not _TOKEN_SHAPE.fullmatch(token):
        raise AppError('signin_token_malformed', 'The Azure CLI answer did not hold a usable token.')
    answered = value.get('tenant')
    if answered is not None and (not isinstance(answered, str) or answered.lower() != tenant.lower()):
        raise SigninBlocked(signin_facts.refused('wrong_tenant', tenant, answered if isinstance(answered, str) else None))
    return token


# Delivery --------------------------------------------------------------------------------------------------------

COLLECT_DEADLINE = 120.0
_SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'intune-iac.py'


def collector_command(tenant, policy, output, descriptor):
    """The collecting child: the product's own capture command, reading its token from the inherited descriptor."""
    return [sys.executable, '-B', str(_SCRIPT), 'capture', '--tenant', tenant, '--policy', policy, '--output', output,
            '--token-fd', str(descriptor)]


def collect(tenant, policy, output, account=None, deadline=DEFAULT_DEADLINE, collect_deadline=COLLECT_DEADLINE):
    """Collect with the reused sign-in: obtain a short-lived read token and hand it to the one collecting child.

    Order: the listing judges the sign-in (a block ends the call with no token command and no child); the token is obtained;
    a pipe is created, the token is written to it and its write end is closed; the child is started with the read end as
    its only extra descriptor (pass_fds), a scrubbed environment and no stdin; the parent closes the read end at once.
    The token is never an argument, never in either environment, never written to a file, and never printed. A child that
    echoes it has its whole output withheld.
    """
    if signin_facts.shown(policy, signin_facts.GUID) is None:
        raise AppError('signin_policy_invalid', 'The policy must be a GUID.')
    if not isinstance(output, str) or not output or '\x00' in output:
        raise AppError('signin_output_invalid', 'The output path is not valid.')
    try:
        token = obtain_token(tenant, account, deadline)
    except SigninBlocked as blocked:
        return {'status': 'blocked', 'signin': blocked.verdict, 'collector_started': False}
    read_end, write_end = os.pipe()
    try:
        try:
            os.write(write_end, token.encode('ascii'))  # at most TOKEN_LIMIT bytes: fits the pipe buffer, never blocks
        finally:
            os.close(write_end)
        try:
            done = subprocess.run(collector_command(tenant, policy, output, read_end), stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=scrubbed_environment(),
                                  pass_fds=(read_end,), close_fds=True, timeout=collect_deadline, shell=False)
        except subprocess.TimeoutExpired:
            raise AppError('signin_collect_deadline', 'The collecting command did not finish in time and was stopped.') from None
        except OSError:
            raise AppError('signin_collect_unavailable', 'The collecting command could not be started.') from None
    finally:
        os.close(read_end)
    return _collector_result(done, token)


def _collector_result(done, token):
    needle = token.encode('ascii')
    if needle in done.stdout or needle in done.stderr:
        return {'status': 'failed', 'error_code': 'collector_output_withheld', 'collector_started': True,
                'child_exit': done.returncode}
    if done.returncode != 0:
        return {'status': 'failed', 'error_code': _error_code(done.stderr), 'collector_started': True,
                'child_exit': done.returncode}
    try:
        value = json.loads(done.stdout.decode('utf-8'))
    except ValueError:
        value = None
    return {'status': 'collected', 'collector_started': True, 'child_exit': 0, 'result': value if isinstance(value, dict) else None}


def _error_code(stderr):
    """The error code on the child's last JSON line of stderr when it is a plain code; never any other text."""
    for line in reversed(stderr.decode('utf-8', 'replace').splitlines()):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        error = value.get('error') if isinstance(value, dict) else None
        code = error.get('code') if isinstance(error, dict) else None
        return signin_facts.shown(code, signin_facts.NAME) or 'collector_failed'
    return 'collector_failed'
