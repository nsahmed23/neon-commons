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


NOT_SHOWN = '<not shown>'
KNOWN_CLOUDS = frozenset({'AzureCloud', 'AzureChinaCloud', 'AzureUSGovernment', 'AzureGermanCloud'})
_UPN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,63}@[A-Za-z0-9][A-Za-z0-9-]{0,62}(?:\.[A-Za-z0-9][A-Za-z0-9-]{0,62}){1,4}')
_PLAIN_HOST = re.compile(r'[a-z0-9][a-z0-9-]{0,23}(?:\.[a-z0-9][a-z0-9-]{0,23}){0,4}', re.I)
_CODE = re.compile(r'[a-z]+(?:_[a-z]+){0,5}')
_ALNUM_RUNS = re.compile(r'[A-Za-z0-9]+')


def _opaque(text):
    """True when the text looks like a credential even though separators divide it into short runs.

    Any run of 24 or more letters and digits; a run of 12 or more with no lower-case letter (a base64 or hex block, not a
    word); a JWT prefix; or 32 or more letters and digits in the local part (48 in the domain) once every separator is removed.
    """
    runs = _ALNUM_RUNS.findall(text)
    if any(len(run) >= 24 or run.startswith('eyJ') or (len(run) >= 12 and not any(c.islower() for c in run)) for run in runs):
        return True
    local, _, domain = text.partition('@')
    return (sum(len(r) for r in _ALNUM_RUNS.findall(local)) >= 32 or sum(len(r) for r in _ALNUM_RUNS.findall(domain)) >= 48)


def shown_name(value):
    """An account or login name as it may be displayed (a GUID, an e-mail-like name or a plain name), else NOT_SHOWN."""
    if not isinstance(value, str):
        return NOT_SHOWN
    if GUID.fullmatch(value):
        return value.lower()
    if (_UPN.fullmatch(value) or (NAME.fullmatch(value) and len(value) <= 64)) and not _opaque(value) and not _TOKENISH.search(value):
        return value
    return NOT_SHOWN


def shown_host(value):
    """A host name as it may be displayed: short labels, no opaque run; else NOT_SHOWN."""
    if isinstance(value, str) and len(value) <= 64 and _PLAIN_HOST.fullmatch(value) and not _opaque(value):
        return value
    return NOT_SHOWN


def shown_cloud(value):
    """A known Azure cloud name, else NOT_SHOWN."""
    return value if isinstance(value, str) and value in KNOWN_CLOUDS else NOT_SHOWN


def shown_code(value):
    """A plain snake_case error code made of lower-case words (no digits, no opaque run), else None."""
    if isinstance(value, str) and len(value) <= 48 and _CODE.fullmatch(value) and all(len(w) <= 20 for w in value.split('_')):
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
        raw_name = user.get('name') if isinstance(user, dict) else None
        raw_cloud = entry.get('cloudName') if isinstance(entry, dict) else None
        state = entry.get('state') if isinstance(entry, dict) else None
        if not (tenant and isinstance(raw_name, str) and raw_name and isinstance(raw_cloud, str) and raw_cloud):
            return _facts('azure', 'unknown', reason='malformed_answer')
        # A value that cannot be displayed safely stays in the list as NOT_SHOWN; the raw value is used only to tell entries apart.
        name, cloud = shown_name(raw_name), shown_cloud(raw_cloud)
        if state in AZURE_ACTIVE_STATES:
            session = SESSION_ACTIVE
        elif state in AZURE_EXPIRED_STATES:
            session = SESSION_EXPIRED
        else:
            unrecognized = True
            continue
        key = (tenant.lower(), raw_name, raw_cloud)
        default = entry.get('isDefault') is True
        if key in seen:
            seen[key]['default'] = seen[key]['default'] or default
            continue
        seen[key] = {'tenant': tenant.lower(), 'account': name, 'cloud': cloud, 'default': default, 'session': session}
        if NOT_SHOWN in (name, cloud):
            seen[key]['ref'] = len(accounts) + 1  # tells hidden entries apart without showing them
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
        if not isinstance(entries, list) or not isinstance(host, str) or not host:
            return _facts('github', 'unknown', reason='malformed_answer')
        for entry in entries:
            raw_login = entry.get('login') if isinstance(entry, dict) else None
            state = entry.get('state') if isinstance(entry, dict) else None
            if not isinstance(raw_login, str) or not raw_login or state not in ('success', 'error', 'timeout'):
                return _facts('github', 'unknown', reason='malformed_answer')
            item = {'host': shown_host(host), 'account': shown_name(raw_login), 'active': entry.get('active') is True,
                    'session': SESSION_ACTIVE if state == 'success' else SESSION_EXPIRED}
            if item['host'] == NOT_SHOWN:
                item['group'] = list(hosts).index(host) + 1  # tells two hidden hosts apart without showing either
            if item['account'] == NOT_SHOWN:
                item['ref'] = len(accounts) + 1
            accounts.append(item)
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
        # Values from elsewhere are filtered again: whatever cannot be displayed safely becomes NOT_SHOWN, never dropped.
        name = shown_name(entry.get('account'))
        ref = entry.get('ref') if isinstance(entry.get('ref'), int) and not isinstance(entry.get('ref'), bool) else len(cleaned) + 1
        if provider == 'azure':
            tenant = shown(entry.get('tenant'), GUID)
            if tenant:
                cleaned.append({'tenant': tenant.lower(), 'account': name, 'cloud': shown_cloud(entry.get('cloud')),
                                'default': entry.get('default') is True, 'session': entry['session'], 'ref': ref})
        else:
            group = entry.get('group') if isinstance(entry.get('group'), int) and not isinstance(entry.get('group'), bool) else 0
            cleaned.append({'host': shown_host(entry.get('host')), 'account': name, 'active': entry.get('active') is True,
                            'session': entry['session'], 'ref': ref, 'group': group})
    return cleaned


def _identity(entry):
    """What tells two entries apart: the shown account, or, for a hidden one, its own reference."""
    return entry['account'] if entry['account'] != NOT_SHOWN else 'hidden-%d' % entry['ref']


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
    if account is not None and shown_name(account) == NOT_SHOWN:
        # Never echoed: only a plain account name is ever repeated in a message.
        return _verdict('azure', 'unknown', 'The account to use is not a plain account name.',
                        'Name the account as the Azure CLI lists it, or leave --account out.', tenant)
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
    defaults = [a for a in active if a['default']]
    names = {_identity(a) for a in active}
    if len(defaults) > 1:
        # Contradictory: more than one account is marked as the one the CLI uses. Never resolved by --account or by order.
        listing = '; '.join(_who(a) for a in defaults)
        return _verdict('azure', 'several_accounts',
                        'The Azure CLI marks several accounts as its default: %s. The product does not pick one.' % listing,
                        'Make exactly one the default with: az account set --subscription SUBSCRIPTION (or sign out the others '
                        'with: az logout --username NAME); then run this command again.', tenant, signed_in=active)
    default = defaults[0] if defaults else None
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
    if NOT_SHOWN in (default['account'], default['cloud']):
        return _verdict('azure', 'unknown', 'The account or cloud the Azure CLI uses cannot be displayed safely, so it is not '
                        'used. Signed in to tenant %s as %s (%s).' % (default['tenant'], default['account'], default['cloud']),
                        'Sign in with an account whose name the product can show, or run az account list --output json '
                        'yourself.', tenant, signed_in=active)
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
    return _verdict('azure', 'signed_in', 'Signed in to %s; session freshness is checked when a token is requested.' % _who(default),
                    'No sign-in step is needed.' if tenant else 'Name the context tenant to compare it with this sign-in.',
                    tenant, usable=bool(tenant), signed_in=[default])


def refused(status, tenant, answered=None):
    """A block found at token time rather than in the listing: expired, not_signed_in or wrong_tenant (answered = the tenant)."""
    tenant = shown(tenant, GUID)
    wanted = tenant.lower() if tenant else 'TENANT_ID'
    login = 'az login --tenant %s' % wanted
    if status == 'wrong_tenant':
        other = shown(answered, GUID) or 'another tenant'
        return _verdict('azure', 'wrong_tenant', 'The token request answered for tenant %s; the context names tenant %s. Nothing '
                        'proceeds.' % (other.lower(), wanted), 'Sign in to the tenant the context names: %s; then run this '
                        'command again.' % login, tenant)
    if status == 'expired':
        return _verdict('azure', 'expired', 'The Azure CLI could not refresh the sign-in: it reports it has expired. Nothing '
                        'that needs a token runs.', 'Sign in again to the tenant the context names: %s; then run this command '
                        'again.' % login, tenant)
    return _verdict('azure', 'not_signed_in', 'The Azure CLI reports no usable sign-in.',
                    'Sign in to the tenant the context names: %s; then run this command again.' % login, tenant)


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
    # Several accounts on one host are found before any session filter: a stale one beside a good one is still ambiguous.
    per_host = {}
    for entry in accounts:
        per_host.setdefault((entry['host'], entry['group']), []).append(entry)
    crowded = {key: entries for key, entries in per_host.items() if len(entries) > 1}
    if crowded:
        listing = '; '.join('%s: %s' % (key[0], ', '.join('%s (%s%s)' % (e['account'], 'session ok' if e['session'] == SESSION_ACTIVE
                            else 'session invalid', ', active' if e['active'] else '') for e in entries))
                            for key, entries in sorted(crowded.items(), key=lambda item: item[0]))
        return _verdict('github', 'several_accounts',
                        'Several accounts are listed for one host: %s. The product does not pick one.' % listing,
                        'Make one active with: gh auth switch --user NAME, and remove the others you do not use with: '
                        'gh auth logout --user NAME; then check again.', None, signed_in=active)
    if not active:
        return _verdict('github', 'expired', 'The GitHub sign-in reports an invalid session: %s.' % '; '.join(
            '%s as %s' % (a['host'], a['account']) for a in accounts), 'Sign in again: %s; then check again.' % login, None)
    return _verdict('github', 'signed_in', 'Signed in to %s.' % '; '.join('%s as %s' % (a['host'], a['account']) for a in active),
                    'No sign-in step is needed.', None, usable=False, signed_in=active)
