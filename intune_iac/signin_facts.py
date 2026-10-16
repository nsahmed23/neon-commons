"""Sign-in facts from the answers of the az and gh listings: parsing and judging, pure, offline, no process and no secret.

The input is the text a documented CLI listing printed (az account list, gh auth status --json hosts). Only an allow-list
of fields is read (tenant, account name, cloud, default marker and session state for az; host, login, active marker and
state for gh); every value passes a plain-shape check, and anything else in the answer, including any field that might
carry a credential, is ignored and never copied to the result. A malformed answer yields state unknown with a reason code,
never a fragment of the answer.

States: signed_in, not_signed_in, expired, unknown. The reason is a short code, set when the state is unknown.
"""
from __future__ import annotations

import json
import re

GUID = re.compile(r'[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.@+-]{0,119}')
HOST = re.compile(r'[A-Za-z0-9][A-Za-z0-9.-]{0,119}')
CLOUD = re.compile(r'[A-Za-z][A-Za-z0-9]{0,39}')
# A run this long without a break looks like a token, not a name; a name that carries a JWT prefix is refused too.
_LONG_RUN = re.compile(r'[A-Za-z0-9+/]{32,}')
_TOKENISH = re.compile(r'eyJ|bearer|secret|passw|=', re.I)
SESSION_ACTIVE, SESSION_EXPIRED = 'active', 'expired'
AZURE_ACTIVE_STATES = frozenset({'Enabled'})
AZURE_EXPIRED_STATES = frozenset({'Expired'})


def shown(value, pattern=NAME):
    """The string when it has a plain, bounded shape that cannot be a credential; otherwise None."""
    if (isinstance(value, str) and pattern.fullmatch(value) and not _LONG_RUN.search(value)
            and not _TOKENISH.search(value)):
        return value
    return None


def _facts(provider, state, accounts=(), reason=None):
    return {'provider': provider, 'state': state, 'reason': reason, 'accounts': list(accounts)}


def _load(text):
    if isinstance(text, bytes):
        text = text.decode('utf-8', 'strict')
    if not isinstance(text, str):
        raise ValueError('not text')
    return json.loads(text) if text.strip() else None


def parse_azure(text):
    """Facts from `az account list --output json`: one entry per distinct (tenant, account, cloud)."""
    try:
        value = _load(text)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return _facts('azure', 'unknown', reason='malformed_answer')
    if value is None:
        return _facts('azure', 'unknown', reason='malformed_answer')
    if not isinstance(value, list):
        return _facts('azure', 'unknown', reason='malformed_answer')
    if not value:
        return _facts('azure', 'not_signed_in')
    accounts, seen, unrecognized = [], {}, False
    for entry in value:
        user = entry.get('user') if isinstance(entry, dict) else None
        tenant = shown(entry.get('tenantId'), GUID) if isinstance(entry, dict) else None
        name = shown(user.get('name')) if isinstance(user, dict) else None
        cloud = shown(entry.get('cloudName'), CLOUD) if isinstance(entry, dict) else None
        state = entry.get('state') if isinstance(entry, dict) else None
        if not (tenant and name and cloud):
            return _facts('azure', 'unknown', reason='malformed_answer')
        if state in AZURE_ACTIVE_STATES:
            session = SESSION_ACTIVE
        elif state in AZURE_EXPIRED_STATES:
            session = SESSION_EXPIRED
        else:
            unrecognized = True
            continue
        key = (tenant.lower(), name, cloud)
        default = entry.get('isDefault') is True
        if key in seen:
            seen[key]['default'] = seen[key]['default'] or default
            continue
        seen[key] = {'tenant': tenant.lower(), 'account': name, 'cloud': cloud, 'default': default, 'session': session}
        accounts.append(seen[key])
    if not accounts:
        return _facts('azure', 'unknown', reason='account_state_unrecognized' if unrecognized else 'malformed_answer')
    if any(a['session'] == SESSION_ACTIVE for a in accounts):
        return _facts('azure', 'signed_in', accounts)
    return _facts('azure', 'expired', accounts)


def parse_github(text, code, error_text):
    """Facts from `gh auth status --json hosts` (exit code and the text of stderr decide a not-signed-in answer)."""
    try:
        value = _load(text)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return _facts('github', 'unknown', reason='malformed_answer')
    if value is None:
        # No document: gh says it is not logged in on stderr and exits non-zero; anything else is not established.
        if code and isinstance(error_text, str) and 'not logged in' in error_text.lower():
            return _facts('github', 'not_signed_in')
        return _facts('github', 'unknown', reason='malformed_answer' if not code else 'command_failed')
    hosts = value.get('hosts') if isinstance(value, dict) else None
    if not isinstance(hosts, dict):
        return _facts('github', 'unknown', reason='malformed_answer')
    accounts = []
    for host, entries in hosts.items():
        if not isinstance(entries, list) or shown(host, HOST) is None:
            return _facts('github', 'unknown', reason='malformed_answer')
        for entry in entries:
            login = shown(entry.get('login')) if isinstance(entry, dict) else None
            state = entry.get('state') if isinstance(entry, dict) else None
            if not login or state not in ('success', 'error', 'timeout'):
                return _facts('github', 'unknown', reason='malformed_answer')
            accounts.append({'host': host, 'account': login, 'active': entry.get('active') is True,
                             'session': SESSION_ACTIVE if state == 'success' else SESSION_EXPIRED})
    if not accounts:
        return _facts('github', 'not_signed_in')
    if any(a['session'] == SESSION_ACTIVE for a in accounts):
        return _facts('github', 'signed_in', accounts)
    return _facts('github', 'expired', accounts)
