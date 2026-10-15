"""The plain `intune-iac simulate` command: read a snapshot and a proposed revision, print the result.

Read-only and offline. It reads the files named on the command line and writes nothing; the result never
authorizes execution. The snapshot comes either from a snapshot document (`--snapshot`) or from a synthetic estate
(`--estate`, optionally with a `--population` of devices, users and memberships the estate does not carry).
"""
from __future__ import annotations

import shutil
import sys

from .io import AppError, load_json
from .sim_eval import simulate
from .sim_model import load_revision, load_snapshot, snapshot_from_estate
from .sim_profile import load_profile
from .sim_render import render_text
from .sim_result import validate_result


def add_parser(commands):
    p = commands.add_parser('simulate', help='Estimate the targeting and Settings Catalog conflicts of a proposed revision '
                                             'against a snapshot (read-only, offline; authorizes nothing)')
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument('--snapshot', help='Simulator snapshot document (intune-sim-snapshot/1)')
    source.add_argument('--estate', help='Synthetic estate JSON from `synthetic generate`')
    p.add_argument('--population', help='With --estate: devices, users and memberships the estate does not carry')
    p.add_argument('--revision', required=True, help='Proposed revision document (intune-sim-revision/1)')
    p.add_argument('--profile', help='Semantics profile JSON; the built-in seed profile is used when omitted')
    p.add_argument('--format', choices=('json', 'text'), default='json')
    return p


def command(args):
    if args.population and not args.estate:
        raise AppError('sim_population_requires_estate', 'Use --population only together with --estate.')
    if args.estate:
        estate = load_json(args.estate)
        snapshot = snapshot_from_estate(estate, load_json(args.population) if args.population else None)
    else:
        snapshot = load_snapshot(load_json(args.snapshot))
    revision = load_revision(load_json(args.revision))
    profile = load_profile(load_json(args.profile) if args.profile else {})
    return validate_result(simulate(snapshot, revision, profile).to_schema())


def text_lines(args):
    columns = shutil.get_terminal_size((100, 40)).columns if sys.stdout.isatty() else 100
    return render_text(command(args), max(60, columns))
