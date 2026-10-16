"""Fake az and gh executables for the sign-in tests: canned answers on a temporary search path, arguments recorded.

Nothing here is a real client. Each fake is a small shell script that appends its arguments (one line per call) to a
log, then prints the canned stdout and stderr for the subcommand it was called with, sleeps if told to, and exits with
the canned code. A call with no canned answer exits 127 and is logged, so an unexpected command shows up in the log.
Canned answers are files named <tool>.<first>_<second>.(out|err|code|sleep) in the fake directory.
"""
import json
from pathlib import Path
import stat
import tempfile

SCRIPT = """#!/bin/sh
dir={directory}
printf '%s\\n' "$*" >> "$dir/calls.log"
key="$1_$2"
[ -f "$dir/{tool}.$key.out" ] || exit 127
[ -f "$dir/{tool}.$key.flood" ] && exec yes AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
[ -f "$dir/{tool}.$key.sleep" ] && exec sleep "$(cat "$dir/{tool}.$key.sleep")"
cat "$dir/{tool}.$key.out"
[ -f "$dir/{tool}.$key.err" ] && cat "$dir/{tool}.$key.err" >&2
code=0
[ -f "$dir/{tool}.$key.code" ] && code=$(cat "$dir/{tool}.$key.code")
exit "$code"
"""
TENANT_A = "11111111-1111-4111-8111-111111111111"
TENANT_B = "33333333-3333-4333-8333-333333333333"


class FakeClis:
    """A directory holding fake az and gh; use path_entry() as the first search path entry."""

    def __init__(self, base=None):
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.directory = Path(self.temp.name).resolve()
        for tool in ("az", "gh"):
            path = self.directory / tool
            path.write_text(SCRIPT.format(directory=self.directory, tool=tool))
            path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def cleanup(self):
        self.temp.cleanup()

    def path_entry(self):
        return str(self.directory)

    def answer(self, tool, first, second, out="", err="", code=0, sleep=None):
        base = self.directory / ("%s.%s_%s" % (tool, first, second))
        for suffix, value in (("out", out), ("err", err), ("code", str(code)), ("sleep", None if sleep is None else str(sleep))):
            target = Path(str(base) + "." + suffix)
            if value is None:
                target.unlink(missing_ok=True)
            else:
                target.write_text(value)

    def flood(self, tool, first, second):
        """Make the fake print without end (to test the output ceiling)."""
        self.answer(tool, first, second, out="x")
        Path(str(self.directory / ("%s.%s_%s" % (tool, first, second))) + ".flood").write_text("1")

    def calls(self):
        log = self.directory / "calls.log"
        return log.read_text().splitlines() if log.exists() else []


def azure_account(tenant=TENANT_A, user="alex@example.test", cloud="AzureCloud", default=True, state="Enabled", sub="s1"):
    return {"cloudName": cloud, "id": sub, "isDefault": default, "name": "Subscription " + sub, "state": state,
            "tenantId": tenant, "user": {"name": user, "type": "user"}}


def azure_list(*accounts):
    return json.dumps(list(accounts))


def github_hosts(*entries):
    """gh auth status --json hosts: a mapping from host to a list of account entries (no token field)."""
    hosts = {}
    for host, login, state, active in entries:
        hosts.setdefault(host, []).append({"state": state, "active": active, "host": host, "login": login,
                                           "tokenSource": "keyring", "scopes": "repo", "gitProtocol": "https"})
    return json.dumps({"hosts": hosts})
