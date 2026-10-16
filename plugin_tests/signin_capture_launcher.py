"""Runs the product's real capture command with the capture module's own transport replaced by a local fake (no network).

Used by the sign-in tests as the collecting child: `python -B launcher.py ROOT MODE capture --tenant T --policy P --output O
--token-fd N`. The real cli.main, the real descriptor reader, the real capture code and the real exit-code mapping run; only
the HTTP transport is a fake that answers every request with one canned status and body (MODE: 403, 401-expired,
401-wrong-tenant). The token the transport receives is never printed.
"""
import json
import sys


def main(argv):
    root, mode, args = argv[0], argv[1], argv[2:]
    sys.path.insert(0, root)
    from unittest import mock
    from intune_iac import capture, cli
    answers = {
        '403': (403, {'error': {'code': 'Forbidden', 'message': 'Insufficient privileges.'}}),
        '401-expired': (401, {'error': {'code': 'InvalidAuthenticationToken',
                                        'message': 'Access token has expired or is not yet valid.'}}),
        '401-wrong-tenant': (401, {'error': {'code': 'InvalidAuthenticationTokenTenant',
                                             'message': 'The access token is from the wrong issuer.'}}),
    }
    status, body = answers[mode]

    def factory(token):
        def get(url, *, timeout):
            return status, json.dumps(body).encode(), ()
        return get

    with mock.patch.object(capture, '_http_transport', factory):
        return cli.main(args)


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
