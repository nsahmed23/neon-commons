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


# Judgement -------------------------------------------------------------------------------------------------------

def _clean_accounts(facts, provider):
    """The accounts of a facts dictionary that pass the plain-shape rules; a dictionary from elsewhere is never trusted."""
    listed = facts.get('accounts') if isinstance(facts, dict) else None
    cleaned = []
    for entry in listed if isinstance(listed, list) else []:
        if not isinstance(entry, dict) or entry.get('session') not in (SESSION_ACTIVE, SESSION_EXPIRED):
            continue
        name = shown(entry.get('account'))
        if provider == 'azure':
            tenant, cloud = shown(entry.get('tenant'), GUID), shown(entry.get('cloud'), CLOUD)
            if name and tenant and cloud:
                cleaned.append({'tenant': tenant.lower(), 'account': name, 'cloud': cloud, 'default': entry.get('default') is True,
                                'session': entry['session']})
        else:
            host = shown(entry.get('host'), HOST)
            if name and host:
                cleaned.append({'host': host, 'account': name, 'active': entry.get('active') is True, 'session': entry['session']})
    return cleaned


def _verdict(provider, status, message, next_step, tenant, usable=False, signed_in=()):
    return {'provider': provider, 'status': status, 'usable': usable, 'tenant_wanted': tenant, 'signed_in': list(signed_in),
            'message': message, 'next_step': next_step}


def _who(entry):
    return 'tenant %s as %s (%s)' % (entry['tenant'], entry['account'], entry['cloud'])


def evaluate(facts, tenant=None, account=None):
    """Judge facts against the tenant the context names (and the account the engineer named, if any).

    Pure. status is signed_in, not_signed_in, expired, wrong_tenant, several_accounts, account_mismatch or unknown; usable is
    true only for an azure sign-in that is in the context's tenant, is the one account the CLI would use, and (when the
    engineer named one) is that account. The next step is the exact thing the engineer does; the product runs none of it.
    """
    provider = facts.get('provider') if isinstance(facts, dict) else None
    tenant = shown(tenant, GUID)
    tenant = tenant.lower() if tenant else None
    if provider == 'github':
        return _evaluate_github(facts)
    wanted = tenant or 'TENANT_ID'
    login = 'az login --tenant %s' % wanted
    state = facts.get('state') if isinstance(facts, dict) else None
    accounts = _clean_accounts(facts, 'azure')
    active = [a for a in accounts if a['session'] == SESSION_ACTIVE]
    expired = [a for a in accounts if a['session'] == SESSION_EXPIRED]
    if state == 'not_signed_in':
        return _verdict('azure', 'not_signed_in', 'Not signed in to Azure.',
                        'Sign in to the tenant the context names: %s; then run this command again.' % login, tenant)
    if state not in ('signed_in', 'expired') or not accounts:
        reason = shown(facts.get('reason') if isinstance(facts, dict) else None, NAME) or 'not_established'
        return _verdict('azure', 'unknown', 'The Azure sign-in could not be determined (reason: %s).' % reason,
                        'Run az account list --output json yourself to see the sign-in, or sign in with: %s; then run this '
                        'command again.' % login, tenant)
    in_tenant = [a for a in expired if a['tenant'] == tenant]
    if not active or (tenant and not any(a['tenant'] == tenant for a in active) and in_tenant):
        listing = '; '.join(_who(a) for a in (expired if not active else in_tenant))
        return _verdict('azure', 'expired', 'The Azure sign-in reports itself expired: %s. Nothing that needs a token runs.' % listing,
                        'Sign in again to the tenant the context names: %s; then run this command again.' % login, tenant)
    default = next((a for a in active if a['default']), None)
    names = sorted({a['account'] for a in active})
    if default is None:
        return _verdict('azure', 'unknown', 'The Azure CLI lists signed-in accounts but marks none as the one it uses.',
                        'Choose one with: az account set --subscription SUBSCRIPTION; then run this command again.', tenant,
                        signed_in=active)
    if tenant and default['tenant'] != tenant:
        others = [a for a in active if a is not default]
        extra = (' Other sign-ins listed: %s.' % '; '.join(_who(a) for a in others)) if others else ''
        return _verdict('azure', 'wrong_tenant',
                        'Signed in to %s; the context names tenant %s. Nothing proceeds.%s' % (_who(default), tenant, extra),
                        'Sign in to the tenant the context names: %s; then run this command again.' % login, tenant, signed_in=active)
    if len(names) > 1 and account != default['account']:
        listing = '; '.join('%s%s' % (_who(a), ' (the CLI uses this one)' if a is default else '') for a in active)
        tail = '' if account is None else ' You named %s.' % account
        return _verdict('azure', 'several_accounts',
                        'Several accounts are signed in: %s. The product does not pick one.%s' % (listing, tail),
                        'Name the account with --account NAME; it must be the one the Azure CLI uses by default (change that '
                        'with: az account set --subscription SUBSCRIPTION), or sign out the others with: az logout --username NAME.',
                        tenant, signed_in=active)
    if account is not None and account != default['account']:
        return _verdict('azure', 'account_mismatch',
                        'You named account %s; the Azure CLI uses %s by default. Nothing proceeds.' % (account, default['account']),
                        'Sign in with that account (az login --tenant %s) or leave --account out.' % wanted, tenant, signed_in=active)
    return _verdict('azure', 'signed_in', 'Signed in to %s.' % _who(default),
                    'No sign-in step is needed.' if tenant else 'Name the context tenant to compare it with this sign-in.',
                    tenant, usable=bool(tenant), signed_in=[default])


def _evaluate_github(facts):
    accounts = _clean_accounts(facts, 'github')
    state = facts.get('state') if isinstance(facts, dict) else None
    login = 'gh auth login'
    if state == 'not_signed_in':
        return _verdict('github', 'not_signed_in', 'Not signed in to GitHub.', 'Sign in: %s; then check again.' % login, None)
    if state not in ('signed_in', 'expired') or not accounts:
        reason = shown(facts.get('reason') if isinstance(facts, dict) else None, NAME) or 'not_established'
        return _verdict('github', 'unknown', 'The GitHub sign-in could not be determined (reason: %s).' % reason,
                        'Run gh auth status yourself to see it.', None)
    active = [a for a in accounts if a['session'] == SESSION_ACTIVE]
    if not active:
        return _verdict('github', 'expired', 'The GitHub sign-in reports an invalid session: %s.' % '; '.join(
            '%s as %s' % (a['host'], a['account']) for a in accounts), 'Sign in again: %s; then check again.' % login, None)
    per_host = {}
    for entry in active:
        per_host.setdefault(entry['host'], []).append(entry)
    crowded = {host: entries for host, entries in per_host.items() if len(entries) > 1}
    if crowded:
        listing = '; '.join('%s: %s' % (host, ', '.join(e['account'] + (' (active)' if e['active'] else '') for e in entries))
                            for host, entries in sorted(crowded.items()))
        return _verdict('github', 'several_accounts',
                        'Several accounts are signed in to one host: %s. The product does not pick one.' % listing,
                        'Make one active with: gh auth switch --user NAME; then check again.', None, signed_in=active)
    return _verdict('github', 'signed_in', 'Signed in to %s.' % '; '.join('%s as %s' % (a['host'], a['account']) for a in active),
                    'No sign-in step is needed.', None, usable=False, signed_in=active)
