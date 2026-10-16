"""The cases whose `signin status --json` (and `signin collect`) output is a compatibility contract (PKG-SETUP-5C round 2).

Each case is a set of fake CLI answers and the arguments of one command. The golden files under plugin_tests/fixtures/signin_golden
were captured from the CLI at 5404dd5 (before the readable text form), so they hold the former keys and values exactly. A later
version may add only the keys in ADDITIVE_KEYS; every former key keeps its former value.
"""
import base64
import json
import time

from plugin_tests.signin_fakes import TENANT_A, TENANT_B, azure_account, azure_list, github_hosts

POLICY = '22222222-2222-4222-8222-222222222222'
LONG_UPN = 'alexander.morgan@contoso.onmicrosoft.com'
ADDITIVE_KEYS = frozenset({'detail_code', 'rule', 'readable_message'})
OUT = '{OUT}'  # replaced by a new folder name under a temporary directory at run time


def _part(value):
    return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b'=').decode()


def _token(**claims):
    return _part({'alg': 'none'}) + '.' + _part(claims) + '.' + 'sig' * 8


def _token_answer(token):
    return json.dumps({'accessToken': token, 'expires_on': int(time.time()) + 3600, 'expiresOn': '2099-01-01 00:00:00.000000',
                       'tenant': TENANT_A, 'tokenType': 'Bearer'})


def _az(*accounts):
    return [('az', 'account', 'list', azure_list(*accounts))]


def _gh(login):
    return [('gh', 'auth', 'status', github_hosts(('github.com', login, 'success', True)))]


STATUS = ['signin', 'status', '--tenant', TENANT_A]
# name: (answers, argv)
CASES = {
    # Round 3: the paths that render hidden names inside a listing, and a GitHub login that is only an unbroken run.
    'two_defaults_hidden_accounts': (_az(azure_account(user=LONG_UPN), azure_account(user='alex.password@example.test', default=True)),
                                     STATUS),
    'several_hidden_accounts': (_az(azure_account(user=LONG_UPN), azure_account(user='alex.password@example.test', default=False),
                                    azure_account(user='ABCDEF123456!', default=False)), STATUS),
    'cred_github_unbroken_run': (_gh('a' * 30), ['signin', 'status', '--provider', 'github']),
    'two_defaults': (_az(azure_account(), azure_account(user='sam@example.test', default=True)), STATUS),
    'two_default_rows_one_account': (_az(azure_account(sub='s1'), azure_account(sub='s2')), STATUS),
    'cred_token_prefix': (_az(azure_account(user='ghp_abc1234')), STATUS),
    'cred_jwt_prefix': (_az(azure_account(user='eyJhbGciOiJIUzI1NiJ9.x@contoso.com')), STATUS),
    'cred_unbroken_run': (_az(azure_account(user='a' * 30 + '@contoso.com')), STATUS),
    'cred_prefix_and_run': (_az(azure_account(user='ghp_' + 'a1' * 12)), STATUS),
    'cred_github': (_gh('ghp_abc1234'), ['signin', 'status', '--provider', 'github']),
    'hidden_long_usable': (_az(azure_account(user=LONG_UPN)), STATUS),
    'hidden_credential_word_usable': (_az(azure_account(user='alex.password@example.test')), STATUS),
    'hidden_odd_characters_usable': (_az(azure_account(user='alex müller@example.test')), STATUS),
    'hidden_capitals_and_bang_usable': (_az(azure_account(user='ABCDEF123456!')), STATUS),
    'hidden_in_wrong_tenant': (_az(azure_account(user=LONG_UPN)), ['signin', 'status', '--tenant', TENANT_B]),
    'hidden_sovereign_cloud': (_az(azure_account(user=LONG_UPN, cloud='AzureChinaCloud')), STATUS),
    'hidden_github_login': (_gh('alexander.morgan.longname1234'), ['signin', 'status', '--provider', 'github']),
    'collect_opaque_token': (_az(azure_account()) + [('az', 'account', 'get-access-token', _token_answer('opaque-' + 'A' * 40))],
                             ['signin', 'collect', '--tenant', TENANT_A, '--policy', POLICY, '--output', OUT]),
    'collect_token_without_account_claim': (
        _az(azure_account()) + [('az', 'account', 'get-access-token', _token_answer(_token(tid=TENANT_A)))],
        ['signin', 'collect', '--tenant', TENANT_A, '--policy', POLICY, '--output', OUT]),
}
