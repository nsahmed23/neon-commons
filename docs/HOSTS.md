# Host setup and measured support

The package provides a shared skill and a relocatable Python CLI. Install the
pinned dependencies from `requirements-runtime.txt`, then run
`python scripts/intune-iac.py doctor`. Installation does not authorize cloud
operations. The historical measurements below are from 2026-10-02 unless a row
names a later evidence epoch. `research/completion/host-qualification.json`
contains the historical command receipts and hashes; later rows link their
separate qualification records.

## Measured surfaces

| Surface | Result | Evidence and limit |
| --- | --- | --- |
| Linux x86_64, kernel 6.18.44, Python 3.12.14 | Observed environment | This does not establish other OS/version combinations. |
| Local repository CLI, wizard, verification and action runner | 7 checks passed | Actual subprocesses against a constructed offline repository; includes the MCP check below. |
| Local stdio MCP | Passed | Actual `initialize` and `tools/call` exchange; not registration or use inside Codex/Claude. |
| Linux PTY wizard | Passed | Real generation/finish interaction and independent output verification; not a native host UI test. |
| Codex CLI 0.159.2 | Version and help measured | `/opt/codex/bin/codex`; plugin discovery, installation, skill loading and model triggering **not run**. |
| Claude Code | Not run | `claude` executable absent. |
| Native Windows and Git Bash/MSYS | Not run | No Windows host. Linux PowerShell evidence below does not qualify Windows startup, argv conversion, ACLs or reparse points. |
| Linux PowerShell preview parser/argv | Limited evidence; active after-effect verification incomplete | Initial host had no PowerShell. Official PowerShell 7.6.6 Linux AMD64 later ran a 99-assertion fixture, which preceded an independent Unicode-single-quote finding. Final admission repair has static rejection and ten ordinary-value native argv checks; active adversarial after-replay was rejected by automatic review. Two Utility-module autoload failures remain UNKNOWN. See `POWERSHELL-PREVIEW-QUALIFICATION.md`. |
| macOS | Not run | No macOS host. |

The previous `0.154.0-alpha.3` Codex observation is superseded by the measured
`0.159.2` binary. Its local help advertises marketplace add/list and plugin
add/list, but no `plugin validate` command or session `--plugin-dir` flag.
Seven version/help commands exited zero with a minimal environment, closed
inherited descriptors and a child filter allowing AF_UNIX while denying other
socket families. A stricter filter denying all sockets made all seven attempts
exit 101: Codex startup requires a UnixStream for Tokio signal handling. Both
sets of results are retained. **Help is capability evidence, not native
plugin discovery, loading, validation or triggering.**

Before attempting isolated native discovery, a harmless bundled-bubblewrap
namespace probe was run. It failed with `open /proc/9/ns/ns failed: No such
file or directory`; a captured follow-up probe exceeded its 20-second deadline.
Native registration/listing/installation was therefore
not attempted against the real account. No personal marketplace or installed
skills were changed and no model request was made. This is a concrete missing
host qualification, not a pass. The receipt does not claim a filesystem trace
of every read performed during CLI startup.

## Package layout

| File | Role |
| --- | --- |
| `plugin.json` | Portable Agent Plugins 1.0 identity |
| `.codex-plugin/plugin.json` | Codex compatibility presentation and shared skill location |
| `.claude-plugin/plugin.json` | Claude Code metadata |
| `skills/intune-iac/SKILL.md` | Operational workflow |
| `scripts/intune-iac.py` | Python launcher, with runtime siblings at the package root |
| `.agents/plugins/marketplace.json` | Local marketplace named `intune-iac-local` |

The manifests share package identity/version. OpenAI presentation remains in
the compatibility overlay: an inline `extensions.com.openai` object would
replace that overlay rather than merge with it. Claude discovers the default
`skills/` directory. The manifests do not automatically register an MCP server
or hook. Static manifest/schema checks do not prove any native host loaded the
skill or invoked it correctly.

## Repeat the qualified Linux checks

Run from a prepared checkout, using fresh explicit output directories:

```bash
python scripts/qualify-terminal.py --plugin /absolute/path/intune-iac --output /tmp/new-host-pty
python scripts/qualify-repository.py --plugin /absolute/path/intune-iac --output /tmp/new-host-repository
```

The retained receipts are under `research/completion/host/host-pty/` and
`research/completion/host/host-repository/`. The repository receipt reports
zero cloud and provider calls. Candidate verification remains distinct from
live provider/service qualification.

## Continue Codex qualification on a disposable host account

These are continuation commands, **not commands executed during this build**.
Use a disposable VM or dedicated test account with no personal host config or
credentials. Marketplace registration and plugin installation modify that
test account. The bundled marketplace's `./` source refers to this package.

```bash
codex --version
codex plugin marketplace add /absolute/path/intune-iac --json
codex plugin list --marketplace intune-iac-local --available --json
codex plugin add intune-iac@intune-iac-local --json
codex plugin list --marketplace intune-iac-local --json
```

Save stdout/stderr, host version, manifest hashes and installed-path metadata.
Listing verifies only discovery/registration. A separate, explicitly approved
host session must demonstrate that the operational skill is loaded and invoked
against synthetic input. If using the ChatGPT desktop plugin directory, follow
the official installation/test workflow and retain its observed results.
Do not count a successful list command, static analysis or this documentation
as that session. Model-assisted testing remains unrun here.

## Continue Claude qualification

On a disposable account with Claude Code installed:

```bash
claude --version
claude plugin validate /absolute/path/intune-iac --strict
claude --plugin-dir /absolute/path/intune-iac
```

The official manifest reference documents `validate` and its `--strict`
warning-to-failure behavior. The session command can use a configured model;
run it only as a separately approved host test. In that session, invoke
`/intune-iac:intune-iac` with synthetic input and retain loading, triggering,
workflow and failure evidence. None of these native Claude commands ran here.

## Continue native Windows/PowerShell qualification

In a disposable Windows test checkout with the pinned Python runtime
prerequisites installed:

```powershell
py -3 scripts/intune-iac.py doctor
py -3 -m unittest plugin_tests.test_cli plugin_tests.test_wizard
pwsh -NoProfile -NonInteractive -Command "& py -3 ./scripts/intune-iac.py doctor; exit $LASTEXITCODE"
```

Capture versions, exit codes and complete diagnostics. Follow with native
PowerShell argv/quoting tests and an interactive wizard transcript before
claiming that surface. The Linux PTY harness uses POSIX `pty` and is not a
Windows conformance test. These commands are a continuation plan and may expose
platform blockers; they are not a claim of Windows compatibility.

## Primary references

- [OpenAI plugin packaging and marketplace guidance](https://developers.openai.com/plugins/build/plugins)
- [Agent Plugins 1.0 manifest schema](https://agent-plugins.org/schemas/1.0.0/plugin.schema.json)
- [Claude Code manifest reference](https://code.claude.com/docs/en/plugins-reference)

Official packaging/Claude references were checked on 2026-10-02 after local CLI
help inspection. The installed binary's captured help is the measured Codex
command contract. Documentation, portable schemas and static Plugin Eval
reports remain separate from actual host execution.


## R3 capability reassessment

The 2026-10-07 continuation exposes a working Docker 28.4.0 daemon and a static Codex CLI 0.159.0-alpha.3 binary, SHA-256 `981ade7b03926534c654fd718ced3a9f378b7b2841271e29156f939462d176e9`. This is a different observation from the preserved 0.159.2 host above. A disposable nonroot container with no network, no capabilities, no new privileges, read-only root/input mounts and private temporary home passed explicit boundary probes. No personal account configuration or Docker socket is mounted into that container.

The R3 `native-codex-container` receipt records the exact final runtime's actual discovery/install/list/uninstall outcome, command failures, installed-file hashes and teardown. Read that receipt before claiming native installation qualification; preparation or boundary success alone is insufficient. No model session or skill invocation is run by this procedure. Its container boundary does not qualify the separate protected provider worker, native Windows/macOS, cloud identity or production permissions.

The Linux protected and provider process supervisors must be invoked on the main Python thread; invocation from another thread fails before spawning. Benign background transport threads may remain active. During child acquisition only, the supervisor temporarily defers the Python SIGINT handler as well as masking SIGINT on the spawning thread, so another thread receiving the signal cannot interrupt process-reference acquisition. It restores the original child handler and exact signal mask before the existing guard and restores the parent's original handler and mask after acquiring the reference. Deferred interruption then reaches ordinary process-group cleanup, whose separate deadline remains bounded after spawn. This adds no guarantee for hung preexec startup, parent SIGKILL, power loss, escaped groups or hostile-host containment. Read the R3 scheduler repair's independent receipts separately from the earlier R2 descendant-cleanup evidence.
