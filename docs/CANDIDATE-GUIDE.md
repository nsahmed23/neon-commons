# Candidate guide: install this build, try it, and report on it

This guide is for an engineer who has never seen the product. It takes you from a downloaded archive to a working
copy that you have checked, runs the product on sample data that ships inside the archive, states plainly what the
build does and does not support, and says what to send back if something goes wrong. Nothing in it needs a tenant,
a credential or a network connection after the install.

The product inspects exported Microsoft Intune policy data, maps how the policies relate to groups, filters and
settings, and prepares reviewed local changes. In this build it never changes anything in a real tenant. Every
result you will see below is labelled with the kind of evidence behind it, and every one of them is local.

## What you need

A Linux x86_64 machine with CPython 3.12 and the Python `venv` module (on Debian and Ubuntu that is the
`python3.12-venv` package). Windows Subsystem for Linux (WSL) with an Ubuntu distribution works for evaluating this
build; that does not make native Windows a supported platform (see the support limits below). No other Python
version, no macOS and no native Windows host has been qualified. A terminal window of at least 40 columns by 12 rows
is needed for the visual workspace in the quickstart.

You also need the ten Python wheel files named in `requirements-runtime-linux-x86_64-cp312.lock`. If your machine
can reach the Python package index, the install step fetches them for you. If it cannot, get them once on a machine
that can (the offline variant below) and carry the folder across.

## Check the download

Whoever shared the build with you also shared its digest: the `sha256` value for the archive in the build receipt
(`Intune_IaC_Plugin_Archive_Receipt.json`, produced when the archives were built). Compare it with your copy before
you unpack anything:

```sh
sha256sum Intune_IaC_Plugin_0.9.0.zip
```

The two values must be identical. Then unpack the archive and check every file inside it against the archive's own
`SHA256SUMS` list:

```sh
python3 -m zipfile -e Intune_IaC_Plugin_0.9.0.zip .
cd intune-iac
sha256sum --check --quiet SHA256SUMS
```

`--quiet` prints nothing when every file matches and exits with status 0; any mismatch is printed and the exit
status is not 0. The list includes `BUILD-IDENTITY.json`, the small record that names this build (version, commit,
tree, build time and a content digest); `doctor` prints it later, so a change to it is caught here too. These checks show that the files are the ones the build produced. They do not show who built them:
trust comes from getting the digest from the person who shared the build, over a different route than the archive.

## Install

Everything below runs from the `intune-iac` folder you just unpacked. Create a virtual environment and install the
locked dependencies. The `--require-hashes` flag makes pip refuse any wheel whose SHA-256 differs from the lock, and
`--only-binary :all:` refuses source builds, so nothing runs a build script during the install:

```sh
python3 -m venv .venv
.venv/bin/python -m pip --isolated install --require-hashes --only-binary :all: -r requirements-runtime-linux-x86_64-cp312.lock
```

Offline variant. On a machine with network access, fetch the exact wheels into a folder and check the folder against
the lock; then copy the folder to the target machine:

```sh
.venv/bin/python -m pip --isolated download --require-hashes --only-binary :all: --dest ./wheelhouse -r requirements-runtime-linux-x86_64-cp312.lock
.venv/bin/python scripts/verify-dependencies.py --wheelhouse ./wheelhouse
```

(If the first machine has no environment yet, run the `venv` line above first; pip is all that is needed there.)
On the target machine, install from that local folder only. `--no-index` stops pip from contacting any package
index and `--find-links` names the folder:

```sh
python3 -m venv .venv
.venv/bin/python -m pip --isolated install --no-index --find-links ./wheelhouse --require-hashes --only-binary :all: -r requirements-runtime-linux-x86_64-cp312.lock
```

The hash check applies in both variants: a wheel in the folder that differs from the lock is refused. More detail on
what the lock does and does not prove is in `docs/DEPENDENCIES.md`.

All commands below are written as `intune-iac ...`. That is a shell function you define once in each terminal you
use, so that the commands read the same everywhere and always use this folder's environment:

```sh
intune-iac() { .venv/bin/python -B scripts/intune-iac.py "$@"; }
```

## Quickstart with the bundled sample data

The archive carries one sample export (`examples/supported/input/export.json`, two synthetic policies) and one
matching context file (`examples/context.json`). Every identifier in them is made up. All work files in this
quickstart go into a new folder called `demo` that only you can read:

```sh
mkdir -m 700 demo
```

1. Print the version, then check the host. `doctor` reports installed dependencies, what this host can run, and
   which build you have:

   ```sh
   intune-iac --version
   intune-iac doctor
   ```

   The version is `0.9.0`. In the `doctor` output look for `"status": "ready"` and for the `build` block. For a
   release archive its `status` is `identified` and it names the product version, the commit, the tree, the build
   time and a content digest. Quote that block in any report (see the last section). `live_qualified` and
   `native_host_qualified` are `false` in this build, and that is the truth, not a fault.

2. Survey the sample folder. `start` is read-only and offline; it lists what it found and suggests a next step:

   ```sh
   intune-iac start examples
   ```

   It finds one export (marked synthetic) and one context, and prints the `wizard` command to run next.

3. Run the wizard on the sample export in offline simulation. The journey is a sequence of stages (discovery,
   target, inventory, selection, and on to generation, a reviewed plan, a simulated execution and a handoff). At
   each prompt you type a word. This command answers every prompt for you, so the whole journey runs without
   stopping:

   ```sh
   printf '%s\n' continue continue continue 22222222-2222-4222-8222-222222222222 continue continue continue continue generate continue continue plan approve execute reconcile continue finish | intune-iac wizard --journey --journey-mode simulation --session demo/journey.json --input examples/supported/input/export.json --context examples/context.json --output demo/journey-output
   ```

   The last line of output is a JSON record that ends the run with `"status": "complete_simulation"` and
   `"execution_authorized": false`. The generated, inactive project is in `demo/journey-output`.

   To go through the same journey by hand, run the command after the pipe on its own with a new session file name,
   and type these words at the prompts: `continue` at discovery, target and inventory; the policy identifier
   `22222222-2222-4222-8222-222222222222` at selection; `continue` at preservation, mapping, ownership and atmos;
   `generate` at generation; `continue` at validation and adoption; then `plan`, `approve`, `execute` and
   `reconcile` at the stage of that name; `continue` at convergence; `finish` at handoff. Typing `save` suspends the
   journey, and running the same command again resumes it. A word the current stage does not accept leaves you at
   the same stage.

4. Build a synthetic estate for the workbench with the product's own commands. `synthetic generate` writes a
   reproducible fake estate (three policies, groups, a filter and scope tags; seed 42 is the default, so you get the
   same identifiers every time). `workbench lab-create` puts one of its policies into a local stand-in for the
   service, `workbench init` creates the private observation store, and `workbench collect` reads the stand-in into
   the store:

   ```sh
   intune-iac synthetic generate --output demo/estate --policies 3
   intune-iac workbench lab-create --service-root demo/service --input demo/estate/capture-estate.json --object 45838776-e1bd-566b-a8c5-ad684107e7da
   intune-iac workbench init --root demo/store --tenant ca8a8057-a15f-5caa-8979-0090cd1bc11b
   intune-iac workbench collect --root demo/store --service-root demo/service
   ```

   Each command prints one JSON record. `lab-create` reports `"status": "created"`; the `collect` record shows the
   collections as `"coverage": "complete"`. All of it is marked `synthetic`.

5. Open the workspace, the full-screen view of the store:

   ```sh
   intune-iac workbench workspace --root demo/store --service-root demo/service
   ```

   The Estate list shows the policy. Press Enter to select it (this opens the Inspector, tab 2). Press `3` for the
   Relationships tab: it draws the relationship map, a tree from the policy to what it targets (assignments,
   exclusions, a filter) and what it configures (scope tags, the setting). Up and Down move between nodes, Home
   follows an edge to its other end, Enter inspects a node, and `b` goes back. `?` lists every key, `a` lists the
   actions, and `:` opens a command line that accepts any `workbench` command name. Press `q` to leave; the last
   read-only view is kept for the next start.

   If you have no terminal (a script, a pipe, a window smaller than 40 columns by 12 rows, or `TERM=dumb`), the same
   engine answers as plain text. This prints the relationships of the policy and then leaves:

   ```sh
   printf 'select 45838776-e1bd-566b-a8c5-ad684107e7da\nrelationships\nquit\n' | intune-iac workbench workspace --root demo/store --service-root demo/service
   ```

6. See what the product says it supports. `families` lists every policy, application and script family with its
   support disposition, read from `family-coverage.csv` and the integration manifest in this archive:

   ```sh
   intune-iac workbench families
   ```

   `"available": true` means both files were found. Every family other than the plain Windows Settings Catalog one
   is staged, review-only, reference-only or later.

7. Leave. Close the workspace with `q`, leave the virtual environment's folder as it is, and delete the `demo`
   folder when you are done with it; it holds only the sample outputs:

   ```sh
   rm -r demo
   ```

## Support limits

Read these before you rely on any result.

**Evidence.** Everything in this build is one of three kinds of evidence. SYNTHETIC means generated or bundled
sample data and a modeled stand-in for the service: it shows how the product behaves, and says nothing about any
real tenant. CAPTURE means pages that someone captured from the Microsoft Graph API with the `capture` command and
a read-only token they supplied; the product checks that the pages are consistent, but it cannot prove they came
from the tenant they claim. LABORATORY means a local run of real tooling in a controlled setup, not production.
No result in this build is production evidence.

**What is covered.** The Windows Settings Catalog policy family is the only family carried end to end, and only as
local, reviewed, inactive candidates. Templates, endpoint security, applications and scripts are recognized, listed
(see `families`) and not carried through. There is no write to a live tenant: the build has no route that sends a
change to Microsoft Graph, and `doctor` reports `cloud_apply` as unavailable.

**Simulation.** The `simulate` command estimates which devices a proposed revision would target and which Settings
Catalog values would conflict, from a snapshot or a synthetic estate that you give it. It is synthetic and
review-only: it reads no live data, writes nothing and authorizes nothing, and its filter grammar has not yet been
checked against the vendor documentation. Treat its output as a worked estimate to review, not as a prediction of
what Intune will do.

**Platforms.** Linux x86_64 with CPython 3.12 is the only qualified platform. WSL works for evaluation and does not
qualify native Windows. Native Windows and PowerShell are not qualified: the Windows components in the archive are
inactive pieces with their own local evidence, and the ordinary Windows profile is not enabled.

**The protected worker.** Routes that execute a reviewed plan (the `worker` and protected `service` commands) need an
interpreter and tool set that match the pinned runtime exactly: a qualified Python and the pinned `atmos` 1.230.1
and OpenTofu 1.13.1 executables. A stock Ubuntu host lacks them, so these routes refuse to run there (see
troubleshooting). The quickstart does not need them.

**The terminal.** The visual workspace needs a window of at least 40 columns by 12 rows. Below that it shows only the
session, the hazard and the prompt, never the body.

More detail: `docs/PRODUCT-STATUS.md` (the requirement-to-evidence table and the stages still open),
`docs/OPERATING-PROFILE-R4.md`, `docs/EXTERNAL-GATES-R4.md` and `docs/DATA-HANDLING.md`.

## Troubleshooting

**Reading `doctor`.** `status` is `ready` when the three Python packages (`jsonschema`, `PyYAML`, `python-hcl2`) are
present, and `missing_dependencies` (exit status 5) when one is not; run the install step again with the virtual
environment's interpreter, or check you are using `.venv/bin/python`. `host_capabilities.profiles` lists the routes
the host could support, each with a status, and says nothing about whether the pinned tools are present.
`executables` says whether `atmos`, `tofu`, `pwsh`, `codex` and `claude` were found on the search path. The `build`
block says which build this is. Its `status` is one of: `identified` (every file the archive listed is present and
unchanged), `modified` (the files named in `modified_files` differ from the build, so what you are running is not
the build named above), `inconsistent` (the file list no longer matches the identity record), `unreadable`, or
`not_a_release_build` (a source checkout, which has no build identity).

**Exit status.** 0 is a successful local result. 2 means blocked, partial or unavailable (read the printed reason).
3 means an invalid request or a failed operation. 4 means an output conflict or a held lock (use a new, empty
folder). 5 means missing dependencies. 130 means you interrupted the command.

**`python3 -m venv` fails.** Debian and Ubuntu split the `venv` module into its own package. Install `python3.12-venv`
with your system package manager (this needs administrator rights), delete the half-made `.venv` folder and run the
install again.

**A clock hold.** The workbench records the latest time it has seen. If this host's clock then reads earlier than
that, the product cannot tell how old an observation is, and it holds changes. The message says that the newest
observation's age cannot be established and that collecting again does not clear it. Correct the host clock, or wait
until it reads at or after the recorded time, then restart the workbench. Another form, `clock_floor_invalid`, means
the recorded time cannot be read; changes stay held until it can be.

**A stale observation.** The workbench refuses to prepare a change against an observation it does not consider
fresh, and says why in words such as "the newest observation is not fresh (older than the freshness window); collect
again". Run `intune-iac workbench collect --root demo/store --service-root demo/service` (with your own folders) and
retry. If the message names a different tenant or a different source, you are pointing at the wrong store or
service; collecting again will not help.

**The runtime admission refuses the interpreter.** The `worker` and protected `service` routes bind the exact
interpreter and standard library they run on. On the stock Python 3.12.3 of an Ubuntu WSL test host the product
answers `service_runtime_symlink` with the message "Controller standard-library links are not admitted", because
that standard library is reached through symbolic links. The same refusal was seen from a virtual environment built
on it. There is no setting in this build that overrides it: use the routes that do not need it (everything in
the quickstart), or prepare a qualified runtime as described in `docs/PROTECTED-WORKER-R4.md`.

**A pinned tool is missing.** `doctor` shows `"atmos": false` or `"tofu": false` when the executable is not on the
search path. Commands that need a pinned tool take its path as an argument (for example `repository native` needs
`--executable`) and answer `blocked` with exit status 2 and a list of blockers when it is absent or is not the
pinned version. The pins are in the `wizard --journey` output (`pins`) and in `docs/OPERATING-PROFILE-R4.md`. The quickstart needs
neither tool.

**Nothing draws in the workspace.** Use a larger window, or run it under a real terminal rather than a pipe. With the
text fallback you type commands (`help` lists them) instead of pressing keys.

## Reporting an issue

Send the report to the person or channel that shared this build with you; there is no other destination for it.
Include these four things:

1. The build identity: the `build` block from `intune-iac doctor`, exactly as printed. It names the commit and the
   content digest, so the report can be matched to the exact files.
2. The whole output of `intune-iac doctor`.
3. The exact command you ran, with its arguments, and its exit status (`echo $?` straight after it).
4. The text on the screen when the problem happened: select it in the terminal and paste it, or copy the JSON the
   command printed. A screenshot is fine for the visual workspace, with the tab line and the footer in view.

Never include tokens, passwords, keys, the contents of any environment variable, or tenant data beyond identifiers.
If a command output contains a token, remove it before sending. The sample data and everything in the quickstart
are synthetic, so they are safe to share. Real captured data is not: send only the identifiers needed to find the
problem. `docs/DATA-HANDLING.md` explains what each kind of file can hold.

If the problem is a wrong or surprising result, say what you expected and what you saw, and say which kind of
evidence the screen labelled it with.
