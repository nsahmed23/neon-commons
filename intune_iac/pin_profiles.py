"""Which tool pins a target descriptor or a generation context names, selected by its schema version.

Version 1 documents name the legacy pair (OpenTofu 1.10.0, Atmos 1.199.0) and are readable for reproduction only:
they are labelled legacy_reproduction_only, never silently upgraded, and nothing that reads one writes it back as
version 2. Version 2 documents name the current local qualification. Both pairs are read from native_pins.py, so the
qualification is stated once; this module only decides which profile a document version selects.

The independent oracles (production_oracle.py, reference/) deliberately do not import this module; tests compare
their own literals with the values here.
"""
from __future__ import annotations

from .native_pins import ATMOS_PINS, OPENTOFU_PINS

CURRENT = 'current_local_qualification'
LEGACY = 'legacy_reproduction_only'

CONTEXT_VERSION_LEGACY = '1.0.0'
CONTEXT_VERSION_CURRENT = '2.0.0'
CONTEXT_PROFILES = {CONTEXT_VERSION_LEGACY: LEGACY, CONTEXT_VERSION_CURRENT: CURRENT}

LEGACY_NOTICE = ('This context names the legacy tool pair, which the protected worker does not admit. It is accepted '
                 'to reproduce earlier output only; start a new context (schema_version 2.0.0) for the current pins.')


def entry(pins, profile):
    """The single (sha256, version) pair native_pins.py holds for a profile."""
    matches = [(sha, record['version']) for sha, record in pins.items() if record['profile'] == profile]
    if len(matches) != 1:
        raise RuntimeError('native_pins.py must hold exactly one ' + profile + ' entry per tool')
    return matches[0]


def tools(profile):
    """OpenTofu and Atmos version and executable digest for a profile."""
    engine_sha, engine_version = entry(OPENTOFU_PINS, profile)
    atmos_sha, atmos_version = entry(ATMOS_PINS, profile)
    return {'engine_version': engine_version, 'engine_sha256': engine_sha,
            'atmos_version': atmos_version, 'atmos_sha256': atmos_sha}


def context_profile(context):
    """The profile a context selects by schema_version, with its tool pins, or None for an unknown version."""
    version = context.get('schema_version') if isinstance(context, dict) else None
    profile = CONTEXT_PROFILES.get(version) if type(version) is str else None
    if profile is None:
        return None
    return dict(tools(profile), profile=profile, schema_version=version)


def context_pin_report(context):
    """What a result says about the pins a context selects; the profile is None when the declared pins disagree.

    A context that spells a pin which its own version does not select (for example schema 2.0.0 with OpenTofu 1.10.0)
    is not a legacy context and not a current one, so it has no profile.
    """
    selected = context_profile(context)
    if selected is None or any(key in context and context[key] != selected[key]
                               for key in ('engine_version', 'atmos_version')):
        return {'pin_profile': None}
    report = {'pin_profile': selected['profile'],
              'pins': {'opentofu': selected['engine_version'], 'atmos': selected['atmos_version']}}
    if selected['profile'] == LEGACY:
        report['pin_notice'] = LEGACY_NOTICE
    return report
