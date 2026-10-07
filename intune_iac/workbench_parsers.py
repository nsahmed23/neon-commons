"""Portable command declarations, without importing native execution adapters.

Help remains usable when an optional host capability is absent. Executing a
route still requires that adapter's actual platform and authority checks.
"""


def add_observer_parser(sub):
    create = sub.add_parser('observer-create', help='Create an inactive scoped Graph reader job; no network or credentials read')
    for name in ('root', 'tenant', 'client', 'principal', 'secret-env', 'output'):
        create.add_argument('--' + name, required=True)
    create.add_argument('--object', action='append', required=True)
    create.add_argument('--interval-seconds', type=float, default=300)
    create.add_argument('--max-duration-seconds', type=float, default=120)
    create.add_argument('--laboratory-fixture', help='Explicit hash-pinned recorded-response profile; cannot establish live authentication')
    for name in ('observer-run', 'observer-status', 'observer-scheduler'):
        command = sub.add_parser(name)
        command.add_argument('--job', required=True)
        if name == 'observer-scheduler':
            command.add_argument('--output', required=True)


def add_worker_parser(commands):
    parser = commands.add_parser('worker', help='Durable service job contract; local network-denied qualification profiles only')
    routes = parser.add_subparsers(dest='worker_command', required=True)
    for name in ('prepare', 'review', 'status', 'attach', 'run', 'cancel', 'reconcile'):
        route = routes.add_parser(name)
        route.add_argument('--job-root', required=True)
        route.add_argument('--policy', required=True)
        if name == 'prepare':
            route.add_argument('--executor-root', required=True)
            route.add_argument('--context', required=True)
        if name == 'run':
            route.add_argument('--receipt', required=True)
