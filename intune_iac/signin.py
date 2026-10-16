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

import os
import shutil
import subprocess

from . import signin_facts

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


def detect_github(deadline=DEFAULT_DEADLINE):
    """GitHub facts from the CLI's own status: host, account, whether a session exists."""
    try:
        code, out, err = _run(['gh', 'auth', 'status', '--json', 'hosts'], deadline)
    except CliError as error:
        return _unknown('github', error.code)
    return signin_facts.parse_github(out, code, err)
