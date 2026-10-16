"""Sign-in facts from the answers of the az and gh listings: parsing and judging, pure, offline, no process and no secret.

The input is the text a documented CLI listing printed (az account list, gh auth status --json hosts). Only an allow-list
of fields is read (tenant, account name, cloud, default marker and state word for az; host, login, active marker and
state for gh); every value passes a plain-shape check, and anything else in the answer, including any field that might
carry a credential, is ignored and never copied to the result. A malformed answer yields state unknown with a reason code,
never a fragment of the answer.

Each listed entry keeps the state word the listing printed, as listing_state, when it is one of the known plain words. It is
never called a session: az's word (Enabled, Expired) is the state of the listed subscription and says nothing about whether
the sign-in is still fresh, which is learnt only when a token is requested; gh's word (success, error, timeout) is the result
of gh's own check of the stored login.

States: signed_in, not_signed_in, subscription_expired (az lists every subscription as Expired: the subscription's state, not
sign-in expiry, which only a token request shows), unknown, and invalid (gh reported error for a login it checked, which is
any error after same-host ambiguity is resolved). Verdict statuses add expired (found at token time), wrong_tenant,
several_accounts, account_mismatch and account_binding_unavailable. The reason is a short code, set when the state is unknown
or invalid. These status values, the messages and the keys are a compatibility contract of `signin status --json` and
`signin collect`: the finer distinctions (two_defaults, credential_shaped_name, the matched rule, a readable sentence) are in
evaluate_with_presentation(), for the text view only, and never in the verdict.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import textwrap

GUID = re.compile(r'[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.@+-]{0,119}')
HOST = re.compile(r'[A-Za-z0-9][A-Za-z0-9.-]{0,119}')
CLOUD = re.compile(r'[A-Za-z][A-Za-z0-9]{0,39}')
# A run this long without a break looks like a token, not a name; a name that carries a JWT prefix is refused too.
_LONG_RUN = re.compile(r'[A-Za-z0-9+/]{32,}')
_TOKENISH = re.compile(r'eyJ|bearer|secret|passw|=', re.I)
# The known plain state words, exactly as the listings print them; an entry with any other word is not used.
AZURE_ACTIVE_STATES = frozenset({'Enabled'})
AZURE_EXPIRED_STATES = frozenset({'Expired'})
GITHUB_USABLE, GITHUB_ERROR, GITHUB_TIMEOUT = 'success', 'error', 'timeout'
LISTING_STATES = {'azure': AZURE_ACTIVE_STATES | AZURE_EXPIRED_STATES,
                  'github': frozenset({GITHUB_USABLE, GITHUB_ERROR, GITHUB_TIMEOUT})}
# Every placeholder in a printed step is followed by its meaning in brackets, so no step is mistaken for one to paste as is.
TENANT_PLACEHOLDER = 'TENANT_ID (the tenant id the context names)'
SUBSCRIPTION_STEP = 'az account set --subscription SUBSCRIPTION (the subscription id or name)'
LOGOUT_STEP = 'az logout --username NAME (the account name to sign out)'
DEFAULT_ACCOUNT_STEP = 'az account show --query user.name -o tsv'
GITHUB_RECHECK = 'intune-iac signin status --provider github'


def shown(value, pattern=NAME):
    """The string when it has a plain, bounded shape that cannot be a credential; otherwise None."""
    if (isinstance(value, str) and pattern.fullmatch(value) and not _LONG_RUN.search(value)
            and not _TOKENISH.search(value)):
        return value
    return None


NOT_SHOWN = '<not shown>'
PUBLIC_CLOUD = 'AzureCloud'
KNOWN_CLOUDS = frozenset({'AzureCloud', 'AzureChinaCloud', 'AzureUSGovernment', 'AzureGermanCloud'})
_UPN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,63}@[A-Za-z0-9][A-Za-z0-9-]{0,62}(?:\.[A-Za-z0-9][A-Za-z0-9-]{0,62}){1,4}')
_PLAIN_HOST = re.compile(r'[a-z0-9][a-z0-9-]{0,23}(?:\.[a-z0-9][a-z0-9-]{0,23}){0,4}', re.I)
_SEPARATORS = re.compile(r'[^A-Za-z0-9]')
RUN_LIMIT, BLOCK_LIMIT = 24, 12


def _credential_shaped(normalized, limit):
    """The three checks on a value whose separators are already removed."""
    return (len(normalized) >= limit or normalized.startswith('eyJ')
            or (len(normalized) >= BLOCK_LIMIT and not any(c.islower() for c in normalized)))


def opaque(text):
    """True when the text looks like a credential even though separators divide it into short pieces.

    The one helper for names, hosts and the like. Every separator (anything that is not a letter or a digit) is removed first;
    then the normalised value is refused when it has 24 or more characters, starts with a JWT prefix, or has 12 or more
    characters and no lower-case letter (a base64 or hex block, not a word). The whole value is judged, '@' and '.' included
    among the separators, so a credential cannot be divided between the two parts of an e-mail-like name. The cost, accepted as
    fail-closed: an e-mail-like name shows only while its letters and digits total at most 23.
    """
    return _credential_shaped(_SEPARATORS.sub('', text), RUN_LIMIT)


# The error codes the collecting command (capture and the descriptor reader) can produce, and the product's own: a closed set.
CHILD_ERROR_CODES = frozenset({
    'capture_identity_invalid', 'capture_output_unsafe', 'capture_output_conflict', 'capture_platform_unavailable',
    'capture_limit_invalid', 'capture_provenance_invalid', 'capture_token_env_invalid', 'capture_token_missing',
    'capture_token_invalid', 'capture_token_expired', 'capture_token_wrong_tenant', 'capture_transport_invalid', 'capture_write_failed', 'output_conflict',
    'identity_explicit_credential_fd_required', 'identity_credential_fd_type', 'identity_credential_fd_private',
    'identity_credential_fd_limit', 'identity_credential_fd_read_only', 'identity_credential_fd_deadline',
    'identity_credential_invalid', 'identity_credential_fd_not_pending', 'identity_credential_control_character',
    'identity_credential_fd_empty', 'identity_separate_credential_fds_required', 'identity_configuration_invalid',
    'identity_fd_platform_unsupported', 'missing_dependencies', 'invalid_request', 'unknown_command', 'invalid_parameters',
    'collector_failed', 'collector_output_withheld', 'collector_output_invalid', 'collector_output_too_large',
    'cleanup_unconfirmed'})


_TOKEN_PREFIXES = ('ghp_', 'gho_', 'ghu_', 'ghs_', 'ghr_', 'github_pat_')
_UNBROKEN_RUN = re.compile(r'[A-Za-z0-9]{24,}')
_ACCOUNT_ARGUMENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.@+-]{0,127}')
# Why a name is not shown: a closed set of codes, each with the one phrase it prints. A code says which rule matched and carries
# nothing of the name. A credential signature (token_prefix, unbroken_run) blocks use; the other reasons only hide the name.
REASON_TEXT = {
    'token_prefix': 'it starts with a token prefix',
    'unbroken_run': 'it holds an unbroken run of 24 or more letters and digits',
    'credential_word': 'it contains a word that credentials carry',
    'shape': 'it has characters this display does not allow',
    'length': 'it is longer than this display allows',
    'caps_block': 'it is a block of 12 or more capitals and digits, which looks like a key',
}
UNKNOWN_REASON_TEXT = 'it cannot be shown safely'


# The verdict is a plain canonical dict: its keys and values are exactly what `signin status --json` and `signin collect` printed
# before the readable text form, and nothing is attached to it. While it is judged, the facts the text view needs (which hidden
# names were printed, whether two defaults or a credential signature decided it) are noted in a dictionary local to that one
# evaluation. Only evaluate_with_presentation() turns them into a presentation, returned beside the verdict for the text view;
# evaluate() drops them.
# The two causes of account_binding_unavailable, said together in the canonical message; the text view of `signin collect` says
# the one that applied (see collect_lines).
BINDING_CAUSES = 'it is opaque, or carries none of the upn, unique_name or appid claims'
HIDDEN_NAME = 'an account whose name is not shown here (it is longer than this display allows, or shaped like a credential)'
FORMER_SIGNATURE = 'a token prefix or an unbroken run of 24 or more letters and digits'


def hidden_name_text(entry, notes=None):
    """The words for an account whose name is not shown (the canonical wording); the reasons that matched are noted for the text."""
    if notes is not None:
        notes.setdefault('hidden', []).append(_closed_reasons(entry.get('hidden_reasons')))
    return HIDDEN_NAME


def credential_signature(raw):
    """The usability rule: True only for an unbroken credential signature.

    A JWT prefix, a known token prefix (ghp_, gho_, ghu_, ghs_, ghr_, github_pat_), or 24 or more letters and digits with no
    separator. A name that is merely long, or split by separators, is hidden from display (opaque) but is not blocked.
    """
    return isinstance(raw, str) and (raw.startswith('eyJ') or raw.startswith(_TOKEN_PREFIXES) or bool(_UNBROKEN_RUN.search(raw)))


SIGNATURE_FALLBACK = 'its form matches a credential signature'


def _signature_codes(entry):
    return [r for r in (entry.get('hidden_reasons') or ()) if r in ('token_prefix', 'unbroken_run')]


def hidden_reasons(raw):
    """Why shown_name hides this raw name: a list of exactly one code of REASON_TEXT (the first match), or [] for a name it shows.

    The order is the judges' own, deterministic: first the usability judge (credential_signature: a token prefix, then an
    unbroken run), which decides that a name is blocked and is the rule a blocked message names; then shown_name's checks in its
    order (plain shape, then opaque: length, then capitals block, then a credential word). Only the first match is kept, so a
    name never discloses more than one rule. Worked out from the raw name once, when the listing is parsed; it names the rule,
    never any part of the name.
    """
    if not isinstance(raw, str):
        return []
    normalized = _SEPARATORS.sub('', raw)
    checks = (
        ('token_prefix', lambda: raw.startswith('eyJ') or raw.startswith(_TOKEN_PREFIXES)),
        ('unbroken_run', lambda: bool(_UNBROKEN_RUN.search(raw))),
        ('shape', lambda: not (_UPN.fullmatch(raw) or NAME.fullmatch(raw))),
        ('length', lambda: len(normalized) >= RUN_LIMIT or not (_UPN.fullmatch(raw) or len(raw) <= 64)),
        ('caps_block', lambda: len(normalized) >= BLOCK_LIMIT and not any(c.islower() for c in normalized)),
        ('credential_word', lambda: bool(_TOKENISH.search(raw))),
    )
    return next(([code] for code, hit in checks if hit()), [])


def name_digest(raw):
    """What the product keeps of a name it does not show: a digest, so --account can be compared without echoing anything."""
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def account_argument_ok(value):
    """The shape of an --account argument (compared internally, never echoed); it need not be displayable."""
    return isinstance(value, str) and bool(_ACCOUNT_ARGUMENT.fullmatch(value))


def shown_name(value):
    """An account or login name as it may be displayed (a GUID, an e-mail-like name or a plain name), else NOT_SHOWN."""
    if not isinstance(value, str):
        return NOT_SHOWN
    if GUID.fullmatch(value):
        return value.lower()
    if ((_UPN.fullmatch(value) or (NAME.fullmatch(value) and len(value) <= 64)) and not opaque(value) and not _TOKENISH.search(value)
            and not credential_signature(value)):
        return value
    return NOT_SHOWN


def _strict_utf8(text):
    """True when the text encodes as strict UTF-8 (an escaped lone surrogate in the CLI's JSON does not)."""
    try:
        text.encode('utf-8')
    except UnicodeEncodeError:
        return False
    return True


def hidden_internals(raw):
    """The private fields kept beside a hidden name: its digest and whether it carries a credential signature."""
    return {'digest': name_digest(raw), 'digest_folded': name_digest(raw.lower()), 'signature': credential_signature(raw),
            'hidden_reasons': hidden_reasons(raw)}


def shown_host(value):
    """A host name as it may be displayed: short labels, no opaque run; else NOT_SHOWN."""
    if isinstance(value, str) and len(value) <= 64 and _PLAIN_HOST.fullmatch(value) and not opaque(value):
        return value
    return NOT_SHOWN


def shown_cloud(value):
    """A known Azure cloud name, else NOT_SHOWN."""
    return value if isinstance(value, str) and value in KNOWN_CLOUDS else NOT_SHOWN


def shown_code(value):
    """An error code the collecting command or the product can produce (CHILD_ERROR_CODES, a closed set), else None."""
    return value if isinstance(value, str) and value in CHILD_ERROR_CODES else None


def _facts(provider, state, accounts=(), reason=None, **extra):
    return {'provider': provider, 'state': state, 'reason': reason, 'accounts': list(accounts), **extra}


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
    accounts, seen, unrecognized, default_rows, mixed = [], {}, False, 0, False
    for entry in value:
        user = entry.get('user') if isinstance(entry, dict) else None
        tenant = shown(entry.get('tenantId'), GUID) if isinstance(entry, dict) else None
        raw_name = user.get('name') if isinstance(user, dict) else None
        raw_cloud = entry.get('cloudName') if isinstance(entry, dict) else None
        state = entry.get('state') if isinstance(entry, dict) else None
        if not (tenant and isinstance(raw_name, str) and raw_name and isinstance(raw_cloud, str) and raw_cloud
                and _strict_utf8(raw_name)):
            return _facts('azure', 'unknown', reason='malformed_answer')
        # A value that cannot be displayed safely stays in the list as NOT_SHOWN; the raw value is used only to tell entries apart.
        name, cloud = shown_name(raw_name), shown_cloud(raw_cloud)
        if not (isinstance(state, str) and state in LISTING_STATES['azure']):
            unrecognized = True
            continue
        key = (tenant.lower(), raw_name, raw_cloud)
        default = entry.get('isDefault') is True
        if default and state in AZURE_ACTIVE_STATES:
            default_rows += 1  # counted per source row, before rows for one account are merged
        if key in seen:
            seen[key]['default'] = seen[key]['default'] or default
            if seen[key]['listing_state'] != state:
                mixed = True  # rows of one account with different states: never resolved by whichever row came first
            continue
        seen[key] = {'tenant': tenant.lower(), 'account': name, 'cloud': cloud, 'default': default, 'listing_state': state}
        if NOT_SHOWN in (name, cloud):
            seen[key]['ref'] = len(accounts) + 1  # tells hidden entries apart without showing them
        if name == NOT_SHOWN:
            seen[key].update(hidden_internals(raw_name))
        accounts.append(seen[key])
    if not accounts:
        return _facts('azure', 'unknown', reason='account_state_unrecognized' if unrecognized else 'malformed_answer')
    if mixed:
        return _facts('azure', 'unknown', reason='account_state_ambiguous')
    if any(a['listing_state'] in AZURE_ACTIVE_STATES for a in accounts):
        return _facts('azure', 'signed_in', accounts, default_rows=default_rows)
    # Every listed row says Expired. That word describes the subscription; it says nothing about whether the sign-in has expired
    # (only a token request learns that), so the facts carry a subscription state, never an expired sign-in.
    return _facts('azure', 'subscription_expired', accounts, default_rows=default_rows)


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
            if (not isinstance(raw_login, str) or not raw_login or not _strict_utf8(raw_login)
                    or not isinstance(state, str) or state not in LISTING_STATES['github']):
                return _facts('github', 'unknown', reason='malformed_answer')
            item = {'host': shown_host(host), 'account': shown_name(raw_login), 'active': entry.get('active') is True,
                    'listing_state': state}
            if item['host'] == NOT_SHOWN:
                item['group'] = list(hosts).index(host) + 1  # tells two hidden hosts apart without showing either
            if item['account'] == NOT_SHOWN:
                item['ref'] = len(accounts) + 1
                item.update(hidden_internals(raw_login))
            accounts.append(item)
    if not accounts:
        return _facts('github', 'not_signed_in')
    states = {a['listing_state'] for a in accounts}
    # Every host and login is aggregated fail-closed: one error is invalid, else one timeout is unknown, and only all-success is
    # signed in. gh's states are success, error and timeout; none says expired, so no GitHub login is ever reported expired.
    if GITHUB_ERROR in states:
        return _facts('github', 'invalid', accounts, reason='gh_state_error')
    if GITHUB_TIMEOUT in states:
        return _facts('github', 'unknown', accounts, reason='gh_state_timeout')
    return _facts('github', 'signed_in', accounts)


# Judgement -------------------------------------------------------------------------------------------------------

def _closed_reasons(value):
    """The reason codes of a facts entry that belong to the closed set, in order; anything else is dropped."""
    return [r for r in value if isinstance(r, str) and r in REASON_TEXT] if isinstance(value, list) else []


def _clean_accounts(facts, provider):
    """The accounts of a facts dictionary that pass the plain-shape rules; a dictionary from elsewhere is never trusted."""
    listed = facts.get('accounts') if isinstance(facts, dict) else None
    cleaned = []
    for entry in listed if isinstance(listed, list) else []:
        word = entry.get('listing_state') if isinstance(entry, dict) else None
        if not isinstance(word, str) or word not in LISTING_STATES[provider]:
            continue
        # Values from elsewhere are filtered again: whatever cannot be displayed safely becomes NOT_SHOWN, never dropped.
        name = shown_name(entry.get('account'))
        ref = entry.get('ref') if isinstance(entry.get('ref'), int) and not isinstance(entry.get('ref'), bool) else len(cleaned) + 1
        private = {}
        if name == NOT_SHOWN:
            digest = entry.get('digest')
            folded = entry.get('digest_folded')
            private = {'digest': digest if isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest) else None,
                       'digest_folded': folded if isinstance(folded, str) and re.fullmatch(r'[0-9a-f]{64}', folded) else None,
                       'signature': entry.get('signature') is not False,  # unknown counts as a signature: fail closed
                       'hidden_reasons': _closed_reasons(entry.get('hidden_reasons'))}
        if provider == 'azure':
            tenant = shown(entry.get('tenant'), GUID)
            if tenant:
                cleaned.append({'tenant': tenant.lower(), 'account': name, 'cloud': shown_cloud(entry.get('cloud')),
                                'default': entry.get('default') is True, 'listing_state': word, 'ref': ref, **private})
        else:
            group = entry.get('group') if isinstance(entry.get('group'), int) and not isinstance(entry.get('group'), bool) else 0
            cleaned.append({'host': shown_host(entry.get('host')), 'account': name, 'active': entry.get('active') is True,
                            'listing_state': word, 'ref': ref, 'group': group, **private})
    return cleaned


def _matches(entry, account):
    """Whether the account the engineer named is this entry's: compared internally, never echoed."""
    if account is None:
        return True
    if entry['account'] != NOT_SHOWN:
        return entry['account'] == account
    return entry.get('digest') is not None and hmac.compare_digest(entry['digest'], name_digest(account))


def _signature(entry):
    return entry['account'] == NOT_SHOWN and entry.get('signature') is not False


def _identity(entry):
    """What tells two entries apart: the shown account, or, for a hidden one, its own reference."""
    return entry['account'] if entry['account'] != NOT_SHOWN else 'hidden-%d' % entry['ref']


def _verdict(provider, status, message, next_step, tenant, usable=False, signed_in=()):
    # Only display fields leave: the private digest, signature flag and reference stay inside this module.
    shown_keys = ('tenant', 'account', 'cloud', 'default', 'listing_state', 'host', 'active')
    return {'provider': provider, 'status': status, 'usable': usable, 'tenant_wanted': tenant,
            'signed_in': [{k: e[k] for k in shown_keys if k in e} for e in signed_in], 'message': message, 'next_step': next_step}


def _who(entry, notes=None):
    name = entry['account'] if entry['account'] != NOT_SHOWN else hidden_name_text(entry, notes)
    return 'tenant %s as %s (%s)' % (entry['tenant'], name, entry['cloud'])


def evaluate(facts, tenant=None, account=None):
    """Judge facts against the tenant the context names (and the account the engineer named, if any).

    Pure. status is signed_in, not_signed_in, subscription_expired (the listing says Expired: the subscription's state), expired
    (found at token time), invalid (GitHub only), wrong_tenant, several_accounts, account_mismatch or unknown; usable is true only for an azure sign-in that is in the context's tenant, is the one account the CLI would
    use, and (when the engineer named one) is that account. The next step is the exact thing the engineer does, with every
    placeholder marked; the product runs none of it.

    Returns the plain canonical verdict dict and nothing else; the text view uses evaluate_with_presentation.
    """
    return _evaluate(facts, tenant, account, {})


def evaluate_with_presentation(facts, tenant=None, account=None):
    """The text-only route: (the same canonical verdict evaluate() returns, its presentation), from one judgment.

    The presentation is {'code', 'rule', 'sentence'} (see _present). It is a separate object, so it never travels with the verdict.
    """
    notes = {}
    verdict = _evaluate(facts, tenant, account, notes)
    return verdict, _present(verdict, notes)


def _evaluate(facts, tenant, account, notes):
    provider = facts.get('provider') if isinstance(facts, dict) else None
    tenant = shown(tenant, GUID)
    tenant = tenant.lower() if tenant else None
    if provider == 'github':
        return _evaluate_github(facts, notes)
    wanted = tenant or TENANT_PLACEHOLDER
    login = 'az login --tenant %s' % wanted
    who = lambda entry: _who(entry, notes)
    if account is not None and not account_argument_ok(account):
        # Never echoed: the account argument is only compared, never repeated in a message.
        return _verdict('azure', 'unknown', 'The account to use is not a plain account name.',
                        'To see the account the Azure CLI uses by default, run %s; then pass that name with --account NAME '
                        '(that account name), or leave --account out.' % DEFAULT_ACCOUNT_STEP, tenant)
    state = facts.get('state') if isinstance(facts, dict) else None
    accounts = _clean_accounts(facts, 'azure')
    active = [a for a in accounts if a['listing_state'] in AZURE_ACTIVE_STATES]
    expired = [a for a in accounts if a['listing_state'] in AZURE_EXPIRED_STATES]
    if state == 'not_signed_in':
        return _verdict('azure', 'not_signed_in', 'Not signed in to Azure.',
                        'Sign in to the tenant the context names: %s; then run this command again.' % login, tenant)
    if state not in ('signed_in', 'subscription_expired') or not accounts:
        reason = shown(facts.get('reason') if isinstance(facts, dict) else None, NAME) or 'not_established'
        return _verdict('azure', 'unknown', 'The Azure sign-in could not be determined (reason: %s).' % reason,
                        'Run az account list --output json yourself to see the sign-in, or sign in with: %s; then run this '
                        'command again.' % login, tenant)
    in_tenant = [a for a in expired if a['tenant'] == tenant]
    if not active or (tenant and not any(a['tenant'] == tenant for a in active) and in_tenant):
        listing = '; '.join(who(a) for a in (expired if not active else in_tenant))
        return _verdict('azure', 'subscription_expired',
                        'The Azure CLI lists the subscription as Expired for %s. That is the state of the subscription; it does '
                        'not show whether the sign-in itself has expired (a token request shows that). Nothing that needs a token '
                        'runs.' % listing,
                        'Choose another subscription with: %s, or sign in again: %s; then run this command again.'
                        % (SUBSCRIPTION_STEP, login), tenant)
    defaults = [a for a in active if a['default']]
    names = {_identity(a) for a in active}
    rows = facts.get('default_rows') if isinstance(facts, dict) else None
    source_rows = rows if isinstance(rows, int) and not isinstance(rows, bool) else 0
    if len(defaults) > 1 or source_rows > 1:
        # Contradictory: more than one row is marked as the one the CLI uses (counted before identical rows are merged).
        # Never resolved by --account or by order.
        listing = '; '.join(who(a) for a in defaults)
        notes['two_defaults'] = True
        return _verdict('azure', 'several_accounts',
                        'The Azure CLI marks more than one entry as its default: %s. The product does not pick one.' % listing,
                        'Make exactly one the default with: %s, or sign out the others with: %s; then run this command '
                        'again.' % (SUBSCRIPTION_STEP, LOGOUT_STEP), tenant, signed_in=active)
    default = defaults[0] if defaults else None
    if default is None:
        return _verdict('azure', 'unknown', 'The Azure CLI lists signed-in accounts but marks none as the one it uses.',
                        'Choose one with: %s; then run this command again.' % SUBSCRIPTION_STEP, tenant, signed_in=active)
    if tenant and default['tenant'] != tenant:
        others = [a for a in active if a is not default]
        extra = (' Other sign-ins listed: %s.' % '; '.join(who(a) for a in others)) if others else ''
        return _verdict('azure', 'wrong_tenant',
                        'Signed in to %s; the context names tenant %s. Nothing proceeds.%s' % (who(default), tenant, extra),
                        'Sign in to the tenant the context names: %s; then run this command again.' % login, tenant, signed_in=active)
    if _signature(default):
        # The usability rule: only an unbroken credential signature blocks (a merely hidden name does not).
        notes['signature'] = _signature_codes(default)
        return _verdict('azure', 'unknown',
                        'The account name the Azure CLI uses is shaped like a credential (%s), so it is not used and not shown. '
                        'Signed in to tenant %s (%s).' % (FORMER_SIGNATURE, default['tenant'], default['cloud']),
                        'Run az account list --output json yourself to see the sign-in, or sign in with an ordinary account: '
                        '%s; then run this command again.' % login, tenant, signed_in=active)
    if default['cloud'] == NOT_SHOWN:
        return _verdict('azure', 'unknown', 'The cloud the Azure CLI uses is not a known Azure cloud name, so it is not used. '
                        'Signed in to tenant %s as %s.' % (default['tenant'], hidden_name_text(default, notes)
                                                           if default['account'] == NOT_SHOWN else default['account']),
                        'Run az account list --output json yourself to see the sign-in.', tenant, signed_in=active)
    if default['cloud'] != PUBLIC_CLOUD:
        # This build's collector reads the public Graph endpoint and the token is requested for the public Graph resource, so a
        # sovereign-cloud sign-in is refused by cloud rather than judged usable.
        return _verdict('azure', 'unknown', 'The Azure CLI is signed in to %s in the %s cloud; this build collects only from the '
                        'public Azure cloud (%s), so that sign-in is not used.' % (
                            'tenant %s as %s' % (default['tenant'], hidden_name_text(default, notes)
                                                 if default['account'] == NOT_SHOWN else default['account']),
                            default['cloud'], PUBLIC_CLOUD),
                        'Switch the Azure CLI to the public cloud with: az cloud set --name %s; then sign in to the tenant the '
                        'context names: %s; then run this command again.' % (PUBLIC_CLOUD, login), tenant, signed_in=active)
    if len(names) > 1 and not (account is not None and _matches(default, account)):
        listing = '; '.join('%s%s' % (who(a), ' (the CLI uses this one)' if a is default else '') for a in active)
        tail = '' if account is None else ' The account you named is not the one the CLI uses by default.'
        return _verdict('azure', 'several_accounts',
                        'Several accounts are signed in: %s. The product does not pick one.%s' % (listing, tail),
                        'Name the account with --account NAME (your account name); it must be the one the Azure CLI uses by '
                        'default, which you change with: %s. Or sign out the others with: %s.' % (SUBSCRIPTION_STEP, LOGOUT_STEP),
                        tenant, signed_in=active)
    if account is not None and not _matches(default, account):
        return _verdict('azure', 'account_mismatch',
                        'The account you named is not the one the Azure CLI uses by default. Nothing proceeds.',
                        'To see the account the Azure CLI uses by default, run %s yourself. Then sign in with the account you '
                        'named: az login --tenant %s; or run this command again without --account.' % (DEFAULT_ACCOUNT_STEP, wanted),
                        tenant, signed_in=active)
    message = 'Signed in to %s; session freshness is checked when a token is requested.' % who(default)
    next_step = ('No sign-in step is needed.' if tenant else
                 'To compare this sign-in with the context tenant, run: intune-iac signin status --tenant %s.' % TENANT_PLACEHOLDER)
    if account is not None:
        message += ' The account matches.'  # the product says so; it never prints either value
    elif default['account'] == NOT_SHOWN:
        next_step = ('To see the account name, run %s yourself; to confirm it, pass --account NAME (that account name). '
                     % DEFAULT_ACCOUNT_STEP) + next_step
    return _verdict('azure', 'signed_in', message, next_step, tenant, usable=bool(tenant), signed_in=[default])


def refused(status, tenant, answered=None):
    """A block found at token time rather than in the listing: expired, not_signed_in or wrong_tenant (answered = the tenant).
"""
    tenant = shown(tenant, GUID)
    wanted = tenant.lower() if tenant else TENANT_PLACEHOLDER
    login = 'az login --tenant %s' % wanted
    if status == 'wrong_tenant':
        other = shown(answered, GUID) or 'another tenant'
        return _verdict('azure', 'wrong_tenant', 'The token request answered for tenant %s; the context names tenant %s. Nothing '
                        'proceeds.' % (other.lower(), wanted), 'Sign in to the tenant the context names: %s; then run this '
                        'command again.' % login, tenant)
    if status == 'account_binding_unavailable':
        return _verdict('azure', 'account_binding_unavailable',
                        'The token does not say which account it was issued for (%s), so it cannot be tied to the account that '
                        'was judged. Nothing proceeds.' % BINDING_CAUSES,
                        'Sign in again so that the Azure CLI issues a token that names its account: az login --tenant %s; then run '
                        'this command again. If it happens again, report it: a token that names no account cannot be used here.'
                        % wanted, tenant)
    if status == 'account_mismatch':
        return _verdict('azure', 'account_mismatch', 'The token was issued for a different account than the one the Azure CLI '
                        'listed as its default (an unverified claim in the token names another account; such claims may only '
                        'refuse). Nothing proceeds.',
                        'The default account may have changed during the request. To see it, run %s yourself; then run this '
                        'command again (add --account NAME, the account name, to confirm it).' % DEFAULT_ACCOUNT_STEP, tenant)
    if status == 'expired':
        return _verdict('azure', 'expired', 'The Azure CLI could not refresh the sign-in: it reports it has expired. Nothing '
                        'that needs a token runs.', 'Sign in again to the tenant the context names: %s; then run this command '
                        'again.' % login, tenant)
    return _verdict('azure', 'not_signed_in', 'The Azure CLI reports no usable sign-in.',
                    'Sign in to the tenant the context names: %s; then run this command again.' % login, tenant)


def claim_binding(facts, claims):
    """Whether a token's unverified account claim names the default account the listing judged.

    True when it names it, False when it names another, None when the claims name no account (an opaque token, or a JWT with
    no upn, unique_name or appid), which is no evidence either way: unverified claims may only refuse, never permit. A user
    token is judged by upn, else unique_name; a service principal (no such claim) by appid. Compared without regard to case;
    a hidden name only by its digest, so no name is ever printed.
    """
    accounts = [a for a in _clean_accounts(facts, 'azure') if a['listing_state'] in AZURE_ACTIVE_STATES]
    defaults = [a for a in accounts if a['default']]
    if len(defaults) != 1 or not isinstance(claims, dict):
        return None
    claim = next((claims[k] for k in ('upn', 'unique_name') if isinstance(claims.get(k), str) and claims[k]), None)
    if claim is None and isinstance(claims.get('appid'), str) and claims['appid']:
        claim = claims['appid']
    if claim is None or not _strict_utf8(claim):
        return None
    entry = defaults[0]
    if entry['account'] != NOT_SHOWN:
        return entry['account'].lower() == claim.lower()
    return entry.get('digest_folded') is not None and hmac.compare_digest(entry['digest_folded'], name_digest(claim.lower()))


def _evaluate_github(facts, notes):
    accounts = _clean_accounts(facts, 'github')
    state = facts.get('state') if isinstance(facts, dict) else None
    login = 'gh auth login'
    if state == 'not_signed_in':
        return _verdict('github', 'not_signed_in', 'Not signed in to GitHub.', 'Sign in: %s; then run: %s.' % (login, GITHUB_RECHECK),
                        None)
    # A timeout from gh's own check leaves the facts unknown but with the entries listed; they are still judged below.
    if state not in ('signed_in', 'invalid', 'unknown') or not accounts:
        reason = shown(facts.get('reason') if isinstance(facts, dict) else None, NAME) or 'not_established'
        return _verdict('github', 'unknown', 'The GitHub sign-in could not be determined (reason: %s).' % reason,
                        'Run gh auth status yourself to see it.', None)
    active = [a for a in accounts if a['listing_state'] == GITHUB_USABLE]
    # Several accounts on one host are found before any state filter: a failing one beside a good one is still ambiguous.
    per_host = {}
    for entry in accounts:
        per_host.setdefault((entry['host'], entry['group']), []).append(entry)
    crowded = {key: entries for key, entries in per_host.items() if len(entries) > 1}
    if crowded:
        listing = '; '.join('%s: %s' % (key[0], ', '.join('%s (gh state: %s%s)' % (e['account'], e['listing_state'],
                            ', active' if e['active'] else '') for e in entries))
                            for key, entries in sorted(crowded.items(), key=lambda item: item[0]))
        return _verdict('github', 'several_accounts',
                        'Several accounts are listed for one host: %s. The product does not pick one.' % listing,
                        'Make one active with: gh auth switch --user NAME (the login name to use), and remove the others you do '
                        'not use with: gh auth logout --user NAME (a login name you do not use); then run: %s.' % GITHUB_RECHECK,
                        None, signed_in=active)
    if len(active) != len(accounts):
        # Every host is judged, whatever another host says. gh never reports a login as expired: error means its check of the
        # stored login failed, timeout that it did not finish.
        listing = '; '.join('%s as %s (gh state: %s)' % (a['host'], a['account'], a['listing_state']) for a in accounts)
        if any(a['listing_state'] == GITHUB_ERROR for a in accounts):
            return _verdict('github', 'invalid', 'gh reports the GitHub sign-in as invalid (reason: gh_state_error): %s.'
                            % listing, 'Sign in again: %s; then run: %s.' % (login, GITHUB_RECHECK), None)
        return _verdict('github', 'unknown', 'The GitHub sign-in could not be determined (reason: gh_state_timeout): gh did '
                        'not finish checking %s.' % listing, 'Run gh auth status yourself to see it.', None)
    shaped = next((a for a in active if _signature(a)), None)
    if shaped is not None:
        notes['signature'] = _signature_codes(shaped)
        return _verdict('github', 'unknown',
                        'A GitHub login name is shaped like a credential (%s), so it is not used and not shown.' % FORMER_SIGNATURE,
                        'Run gh auth status yourself to see it.', None, signed_in=active)
    hidden = any(a['account'] == NOT_SHOWN for a in active)
    return _verdict('github', 'signed_in', 'Signed in to %s.' % '; '.join(
        '%s as %s' % (a['host'], hidden_name_text(a, notes) if a['account'] == NOT_SHOWN else a['account']) for a in active),
        'To see the login name, run gh auth status yourself.' if hidden else 'No sign-in step is needed.', None, usable=False,
        signed_in=active)


# Text form ---------------------------------------------------------------------------------------------------------

ACCESS_UNKNOWN_LINE = 'Graph, Intune and state-storage access are unknown until a read is attempted.'
_REASON = re.compile(r'\(reason: ([a-z_]+)\)')
_PROVIDER_LABELS = (('azure', 'AZURE'), ('github', 'GITHUB'))


def _printable(text):
    """Text for a terminal: anything that is not printable (a control byte, an escape) becomes a question mark."""
    return ''.join(ch if ch.isprintable() else '?' for ch in str(text))


def _wrap(text, width, first='', rest=''):
    """Rows of at most width columns, broken only at spaces: a GUID, a name or a command word is never split, so a word wider
    than the row stands alone on its row."""
    wrapper = textwrap.TextWrapper(width=max(width, 40), initial_indent=first, subsequent_indent=rest, break_long_words=False,
                                   break_on_hyphens=False)
    return wrapper.wrap(_printable(text)) or [first.rstrip()]


def _hidden_phrase(reasons):
    return 'an account whose name is not shown here (%s)' % (' and '.join(REASON_TEXT[r] for r in reasons) or UNKNOWN_REASON_TEXT)


def _present(verdict, notes):
    """What the text view says beyond the canonical verdict: {'code', 'rule', 'sentence'}.

    code is the finer status (two_defaults, credential_shaped_name) or None; rule is the one matched hiding rule, or None when
    there is none or the sentence names several accounts' rules; sentence is the message with each hidden name's reason in place of
    the generic wording. Built from the verdict and the notes made while it was judged, never by judging again. With no notes it
    presents the canonical message as it is.
    """
    message = verdict.get('message') or ''
    code, rules = None, []
    if notes.get('two_defaults'):
        code = 'two_defaults'
    hidden = notes.get('hidden') or []
    parts = message.split(HIDDEN_NAME)
    if hidden and len(parts) - 1 == len(hidden):
        message = parts[0] + ''.join(_hidden_phrase(reasons) + part for reasons, part in zip(hidden, parts[1:]))
        rules += [reasons[0] for reasons in hidden if reasons]
    if 'signature' in notes and FORMER_SIGNATURE in message:
        codes = notes['signature']
        code = 'credential_shaped_name'
        message = message.replace(FORMER_SIGNATURE, ' and '.join(REASON_TEXT[c] for c in codes) or SIGNATURE_FALLBACK, 1)
        rules += codes[:1]
    return {'code': code, 'rule': rules[0] if rules and len(set(rules)) == 1 else None, 'sentence': message}


def _verdict_line(label, verdict, shown):
    status = verdict.get('status')
    if verdict.get('usable') or (verdict.get('provider') == 'github' and status == 'signed_in'):
        return '%s: READY' % label
    if status == 'signed_in':
        return '%s: REPORTED (no tenant was given to compare)' % label
    reason = _REASON.search(verdict.get('message') or '')
    # The finer code (two_defaults, credential_shaped_name) comes from the presentation; the status stays the former one.
    code = shown['code'] or ('%s: %s' % (status, reason.group(1)) if status == 'unknown' and reason else status)
    return '%s: BLOCKED (%s)' % (label, _printable(code))


def _account_row(verdict, entry):
    name = entry.get('account', NOT_SHOWN)
    if verdict.get('provider') == 'github':
        return '%s on %s%s' % (name, entry.get('host', NOT_SHOWN), ' (active)' if entry.get('active') else '')
    return '%s%s' % (name, ' (default)' if entry.get('default') else '')


def status_lines(report, width, code, shown=None):
    """The text screen for `signin status`: for each provider a verdict line first (READY, REPORTED or BLOCKED with the reason
    code), the tenant wanted and found, the account with the default marked, the cause, and the next step on its own rows;
    then one line that access is unknown, each provider's verdict line again (so a 20-row pane shows it), and what the exit code
    means. Pure: it reads the report's display fields and, per
    provider, the presentation from evaluate_with_presentation (shown); without one it says the canonical message."""
    lines, verdict_lines = [], []
    for name, label in _PROVIDER_LABELS:
        verdict = report.get(name)
        if not isinstance(verdict, dict):
            continue
        if lines:
            lines.append('')
        present = (shown or {}).get(name) or {'code': None, 'rule': None, 'sentence': verdict.get('message') or ''}
        verdict_lines.append(_verdict_line(label, verdict, present))
        lines.append(verdict_lines[-1])
        entries = verdict.get('signed_in') or []
        if name == 'azure':
            found = []
            for entry in entries:
                if entry.get('tenant') not in found:
                    found.append(entry.get('tenant'))
            lines += _wrap('Tenant wanted: %s' % (verdict.get('tenant_wanted') or 'none given'), width)
            lines += _wrap('Tenant found: %s' % (', '.join(found) or 'none'), width)
        for row in [_account_row(verdict, entry) for entry in entries] or ['none usable (the cause below names any listed one)']:
            lines += _wrap('Account: %s' % row, width)
        lines.append('Why:')
        lines += _wrap(present['sentence'], width, '    ', '    ')
        if verdict.get('next_step'):
            lines.append('Next step:')
            lines += _wrap(verdict['next_step'], width, '    ', '    ')
    status = report.get('status')
    meaning = {'ready': '(2 means blocked).', 'reported': '(2 means blocked).', 'blocked': '(0 means ready).'}.get(status, '')
    lines.append('')
    lines += _wrap(ACCESS_UNKNOWN_LINE, width)
    # The provider blocks are longer than a 20-row pane, which then shows only their tail and scrolls the opening verdicts off.
    # Each verdict closes the screen too: the very lines that opened the blocks, built once from the same judgment, never wrapped.
    lines += verdict_lines
    lines += _wrap(('Exit code %s: %s %s' % (code, status, meaning)).strip(), width)
    return lines


# `signin collect`: the text screen -------------------------------------------------------------------------------------

_BINDING_TEXT = {'opaque': 'the token is opaque, so it has no account claim to read',
                 'no_claim': 'it carries none of the upn, unique_name or appid claims',
                 'unusable_claim': 'its account claim is not a usable account name'}
_AFTER_RUN = {'absent': 'not present after this run', 'directory': 'exists after this run',
              'symlink': 'a symbolic link is there after this run', 'other': 'something that is not a directory is there after this run'}
_FAILED_WHY = {'collector_failed': 'The collecting command failed and no more specific error code was reported.',
               'collector_output_invalid': 'The collecting command finished, but its output was not a result this command accepts, '
                                           'so none of it is shown.',
               'collector_output_too_large': 'The collecting command printed more than this command reads, and was stopped.',
               'cleanup_unconfirmed': 'The collecting command left a process running that could not be confirmed gone, so nothing '
                                      'it produced is trusted.'}
_COLLECT_EXIT_MEANING = ('(0 means collected; 2 means partial or blocked; 3 means failed; 4 means the output folder was refused '
                         'before any collecting command started).')


# What the check of the output folder found, one sentence per cause (signin.check_new_output records the cause from the call that
# failed). A cause this table does not know is told as the generic refusal, never as one of these.
_REFUSAL_CAUSE = {
    'exists': 'The output folder already exists, and this command never writes into a path that exists.',
    'ancestor_symlink': 'A folder on the way to the output folder is a symbolic link, and this command does not follow symbolic '
                        'links.',
    'ancestor_not_real_directory': 'A folder on the way to the output folder could not be opened as a real folder.',
    'ancestor_missing': 'A folder on the way to the output folder does not exist; this command creates only the last folder.',
    'name_too_long': 'A name in the output path is too long for the file system to hold.',
    'parent_not_writable': 'The folder that would hold the output folder does not allow this user to write to it.',
    'permission_denied': 'This user is not allowed to open a folder on the way to the output folder.',
}


def _refusal_why(result):
    cause = result.get('cause')
    if cause in _REFUSAL_CAUSE:
        return _REFUSAL_CAUSE[cause]
    if cause == 'unchecked':
        number = result.get('cause_errno')
        return ('The file system refused the check of the output folder%s; no more specific cause was found.'
                % (' (%s)' % number if isinstance(number, str) and re.fullmatch(r'E[A-Z0-9]+', number) else ''))
    return result.get('message') or ''


OUTPUT_DISPLAY_LIMIT = 200
OUTPUT_NOT_SHOWN = '<the output path is not shown>'


def output_display(path):
    """The output path as the text screen may show it: the path itself only when it is printable (no control character of any
    kind, so it cannot start a row or move the cursor), within OUTPUT_DISPLAY_LIMIT, and not credential-shaped (the usability
    rule of credential_signature, on the whole path and on each of its pieces, so a token used as a folder name is caught); else
    one fixed placeholder that holds nothing of the path. It is the same for every rejection, so it does not say which rule
    applied (a value withheld because it may be a credential is not described further). The path is user input and may be
    anything."""
    if (not isinstance(path, str) or not path.isprintable() or len(path) > OUTPUT_DISPLAY_LIMIT
            or credential_signature(path) or any(credential_signature(piece) for piece in re.split(r'[/\\.]', path))):
        return OUTPUT_NOT_SHOWN
    return path


def output_text(path):
    """The output path as the collect screen writes it: through the shared path writer (entry.text_paths), so a path with a
    space or another character the shell would split on is quoted once and can be copied. A path the display rule refuses
    (output_display, or readiness.display_refused: a credential shape, a control character, a character terminal escaping would
    change, or past the limit) is the one fixed placeholder, as it always was; nothing of it is echoed."""
    from .entry import text_paths
    from .readiness import display_refused
    if output_display(path) == OUTPUT_NOT_SHOWN or display_refused(path):
        return OUTPUT_NOT_SHOWN
    return text_paths(None, None)[1](path)


def _partial_reason(result):
    """The one code the verdict line gives for a partial result: the credential problem, else a denied read, else the first reason."""
    inner = result.get('result') or {}
    coverage = inner.get('coverage') or []
    if inner.get('credential_problem'):
        return inner['credential_problem']
    if any(item.get('coverage') == 'access_denied' for item in coverage):
        return 'access_denied'
    return next((item['reason'] for item in coverage if item.get('reason')), None)


def _collect_verdict(result):
    """(the word, the reason) of a collect result: COLLECTED, PARTIAL, FAILED or BLOCKED."""
    status = result.get('status')
    if status == 'collected':
        return 'COLLECTED', None
    if status == 'partial':
        return 'PARTIAL', _partial_reason(result)
    if status == 'failed':
        return 'FAILED', result.get('error_code')
    if status == 'blocked':
        return 'BLOCKED', (result.get('signin') or {}).get('status')
    if status == 'output_conflict':
        return 'BLOCKED', result.get('error_code')
    return str(status).upper(), None


def _collect_why(result, shown):
    """The sentence under Why: for a block, the sign-in message with the one binding cause that applied; for a failure, its cause."""
    if result.get('status') == 'blocked':
        message = (result.get('signin') or {}).get('message') or ''
        cause = _BINDING_TEXT.get(shown.get('binding'))
        return message.replace(BINDING_CAUSES, cause, 1) if cause and BINDING_CAUSES in message else message
    if result.get('status') == 'output_conflict':
        return _refusal_why(result)
    if result.get('status') != 'failed':
        return ''
    if result.get('error_code') == 'collector_output_withheld':
        return result.get('message') or ''
    code = result.get('error_code')
    return _FAILED_WHY.get(code) or 'The collecting command failed with the code %s.' % code


def _collect_steps(result, shown):
    """The next steps, one sentence each and none of them joined to another: [] when nothing is left to do."""
    status, rerun = result.get('status'), shown.get('rerun') or 'intune-iac signin collect'
    again = 'To collect again, run: %s.' % rerun
    if status == 'blocked':
        return [(result.get('signin') or {}).get('next_step') or '']
    if status == 'output_conflict':
        return ['Choose an output folder that does not exist yet, inside a folder that exists and that you can write to.', again]
    if status == 'partial':
        inner, steps = result.get('result') or {}, []
        problem = inner.get('credential_problem')
        if problem:
            steps.append('The collecting command reported the token as %s; sign in again: az login --tenant %s.' % (
                'belonging to a different tenant' if problem == 'token_wrong_tenant' else 'expired', shown.get('tenant')))
        elif any(item.get('coverage') == 'access_denied' for item in inner.get('coverage') or []):
            steps.append('The collecting command reported that a read was denied; ask your administrator whether the signed-in '
                         'account may read these Intune objects.')
        return steps + [again]
    if status == 'failed' and result.get('error_code') == 'collector_output_withheld':
        look = 'If you need to know what is at the output folder, look at it yourself (this command did not open it).'
        if result.get('token_match') == 'full_token':
            return ['Stop and report this: the collecting command printed the access token.', look,
                    'Only after it is reported, to collect again, run: %s.' % rerun]
        return [look, again]
    if status == 'failed':
        return [again]
    return []


def collect_lines(result, width, code, shown=None):
    """The text screen for `signin collect`: the verdict line first (COLLECTED, PARTIAL, FAILED or BLOCKED with its reason), the
    output folder and whether it exists after the run, the collecting command's exit, the coverage per section, the cause and
    the next steps on their own rows, and what the exit code means. Pure: it reads the result's display fields and, from the text
    route (signin.collect_view), the presentation (shown): the output path, what is at it now, the tenant, the command that
    collects again and which binding cause applied. Nothing in it is a token or a name; the result holds none."""
    shown = shown or {}
    word, reason = _collect_verdict(result)
    lines = ['COLLECT: %s' % (word if reason is None else '%s (%s)' % (word, _printable(reason)))]
    inner = result.get('result') or {}
    output = inner.get('output') or shown.get('output')
    started = bool(result.get('collector_started'))
    if output is not None:
        after = shown.get('output_after') or result.get('output_kind_after')
        where = _AFTER_RUN.get(after, 'not looked at') if started else 'no collecting command started, so nothing was written'
        lines += _wrap('Output folder: %s (%s)' % (output_text(output), where), width)
    if not started:
        lines.append('Collecting command: not started')
    elif result.get('child_exit') is None:
        lines.append('Collecting command: stopped without an exit code')
    else:
        lines.append('Collecting command: exit %s' % _printable(result['child_exit']))
    if inner.get('coverage'):
        lines.append('Coverage:')
        for item in inner['coverage']:
            note = ' (%s)' % _printable(item['reason']) if item.get('reason') else ''
            lines.append('    %s: %s%s' % (_printable(item['kind']), _printable(item['coverage']), note))
    why = _collect_why(result, shown)
    if why:
        lines.append('Why:')
        lines += _wrap(why, width, '    ', '    ')
    if result.get('status') == 'partial':
        lines.append('Note:')
        lines += _wrap('This command did not open or remove the output folder and cannot say who created or changed anything in '
                       'it; a new run needs a new folder.', width, '    ', '    ')
    steps = [step for step in _collect_steps(result, shown) if step]
    if steps:
        lines.append('Next step:')
        for number, step in enumerate(steps, 1):
            prefix = '    %d. ' % number if len(steps) > 1 else '    '
            lines += _wrap(step, width, prefix, ' ' * len(prefix))
    lines.append('')
    lines += _wrap('Exit code %s: %s %s' % (code, word.lower(), _COLLECT_EXIT_MEANING), width)
    return lines
