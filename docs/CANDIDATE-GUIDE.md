# Candidate guide: install this build, try it, and report on it

This guide is for an engineer who has never seen the product. It takes you from a downloaded archive to a working
copy that you have checked, runs the product on sample data that ships inside the archive, states plainly what the
build does and does not support, and says what to send back if something goes wrong. Nothing in it needs a tenant,
a credential or a network connection after the install.

The product inspects exported Microsoft Intune policy data, maps how the policies relate to groups, filters and
settings, and prepares reviewed local changes. In this build it never changes anything in a real tenant. Every
result you will see below is labelled with the kind of evidence behind it, and every one of them is local.

The quickstart shows, in this order: a first-run survey that says what is present and what is missing (`start`), the
state of an Azure sign-in you already have (`signin status`), a wizard run on the sample export, the sample estate
the workbench reads, the integration catalog (`catalog`), the visual workspace with its relationship map, the
workflow map (`workbench workflow`, and `:workflow` in the workspace), the engineering view (`engineering`) and the
family table (`workbench families`).

## What you need

A Linux x86_64 machine with CPython 3.12 and the Python `venv` module. On Debian and Ubuntu that is the
`python3.12-venv` package; without it `python3 -m venv` fails, and Troubleshooting gives two ways round that.
Windows Subsystem for Linux (WSL) with an Ubuntu distribution works for evaluating this build; that does not make
native Windows a supported platform (see the support limits below). No other Python version, no macOS and no native
Windows host has been qualified. A terminal window of at least 40 columns by 12 rows is needed for the visual
workspace in the quickstart.

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
tree, build time and a content digest); `doctor` prints it later, so a change to it is caught here too. These checks
show that the files are the ones the build produced. They do not show who built them: trust comes from getting the
digest from the person who shared the build, over a different route than the archive.

## Install

Everything below runs from the `intune-iac` folder you just unpacked. Create a virtual environment and install the
locked dependencies. The `--require-hashes` flag makes pip refuse any wheel whose SHA-256 differs from the lock, and
`--only-binary :all:` refuses source builds, so nothing runs a build script during the install:

```sh
python3 -m venv .venv
.venv/bin/python -m pip --isolated install --require-hashes --only-binary :all: -r requirements-runtime-linux-x86_64-cp312.lock
```

If `python3 -m venv .venv` stops and says that ensurepip is not available, this host's Python cannot put pip into a
new environment. Troubleshooting ("`python3 -m venv` fails") gives the two remedies: install the `python3.12-venv`
package, or make the environment without pip and run pip from a pip wheel file you already hold.

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

## The sample data

Everything the quickstart runs on is synthetic: made up for this build, with no real tenant behind it. Two sources
feed it.

The first ships in the archive: the sample export `examples/supported/input/export.json` (two policies in the made-up
tenant `11111111-1111-4111-8111-111111111111`) and its context file `examples/context.json`. The policy
`22222222-2222-4222-8222-222222222222` (Windows Privacy Pilot) is the one every later step follows. The quickstart
turns these two files into a small estate, all of it under a new folder called `demo`: the project the wizard
generates (`demo/journey-output`, inactive, so nothing in it can run against a tenant); the modeled service
(`demo/service`), a folder that answers the way the service would, so that nothing leaves your machine; and the
observation store (`demo/store`), the private database that the workbench reads and the workspace shows. The same
commands build the same estate every time, with the product's own routes and no file written by hand.

The second source is a generator. `synthetic generate` writes a larger, seeded estate: three policies with groups, a
filter and scope tags. It uses seed 42 unless you give another, so you get the same identifiers on every run. The
last step of the quickstart does it.

Wherever the product shows either, it labels it `synthetic`. A modeled service is a stand-in on your disk, so what
it returns is modeled evidence: it shows how the product behaves and says nothing about any real tenant.

## Quickstart with the bundled sample data

All work files in this quickstart go into a new folder called `demo` that only you can read:

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

2. Look at what is here. `start` surveys a folder and says what it found, what to do next and what is missing. It is
   read-only and offline: it opens no connection and writes nothing.

   ```sh
   intune-iac start examples
   ```

   The screen is titled `INTUNE WORKBENCH: START` and has three parts. FOUND lists what the folder holds: here one
   export (`examples/supported/input/export.json`, marked synthetic, two policies) and one context file
   (`examples/context.json`). Each row ends in state words: `discovered` (found in the folder), `usable here` (the
   product can use it from here, offline), `source-asserted` (the file names a tenant and nothing checks it) and
   `synthetic only` (modeled data, not a live tenant). NEXT numbers what you could run, here the `wizard` command for
   that export (step 4). MISSING says what is absent: `No live discovery connection is configured: offline inspection
   and preparation remain available.` This build holds no live connection, so that line is expected.

   `start` can also say what one goal needs. The goals are `inspect`, `discover`, `adopt` and `change`:

   ```sh
   intune-iac start examples --goal inspect
   ```

   The last line is `GOAL READINESS: inspect (status: ready)`, and the facts behind it stand above it: the host,
   the tenant the inputs name, what the goal needs and what is missing. The other goals report `unknown` or `missing`
   with what they need and the next action. The exit status is 0 whatever the status, because the screen is a report.

3. Check the sign-in state. `signin status` reuses an Azure sign-in you already have (the Azure CLI's own, not a
   connection of this product) and says whether it is usable for a tenant. It runs `az account list --output json`
   and nothing else, and it reads no token:

   ```sh
   intune-iac signin status --tenant 11111111-1111-4111-8111-111111111111
   ```

   The first line is the verdict: `READY` (the CLI lists a usable account in the tenant you named), `REPORTED` (an
   account is signed in but there was no tenant to compare) or `BLOCKED` with a reason code. The sample tenant is made
   up, and a machine with no Azure CLI cannot sign in to it, so the expected answer here is `AZURE: BLOCKED (unknown:
   cli_not_found)`, and the last line says `Exit code 2: blocked (0 means ready).` That is a report, not a fault of the
   install. The screen also says that access to Graph, Intune and state storage is unknown until a read is attempted,
   because a signed-in account does not establish it. A sign-in is never permission for this product to do anything.

4. Run the wizard on the sample export in offline simulation. The journey is a sequence of stages (discovery,
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

5. Build the sample estate for the workbench with the product's own commands. `workbench lab-create` puts the sample
   policy into the modeled service, `workbench init` creates the private observation store for the sample tenant, and
   `workbench collect` reads the modeled service into the store:

   ```sh
   intune-iac workbench lab-create --service-root demo/service --input examples/supported/input/export.json --object 22222222-2222-4222-8222-222222222222
   intune-iac workbench init --root demo/store --tenant 11111111-1111-4111-8111-111111111111
   intune-iac workbench collect --root demo/store --service-root demo/service
   ```

   Each command prints one JSON record. `lab-create` reports `"status": "created"`; the `collect` record shows the
   collections as `"coverage": "complete"`. All of it is marked `synthetic`. Now run `start` on the whole folder
   again:

   ```sh
   intune-iac start demo
   ```

   It finds more than it did at step 2: a `Store` row, a `Service` row (the modeled service), a `Journey` row for the
   finished wizard session and a `Generated` row for its project. The first suggestion under NEXT is `Open the
   workspace`, with its exact command (step 7).

6. Read the integration catalog. `catalog` is the plain list of what this build can do and where each goal stands. It
   is read-only and offline, and it runs no other command:

   ```sh
   intune-iac catalog demo
   ```

   It opens with the line `INTEGRATION CATALOG` and the sentence `No other integration is available in this build.`
   Then it describes the one integration it holds, Microsoft Intune, goal by goal: `GOAL inspect`, `GOAL discover`,
   `GOAL adopt` and `GOAL change`. Each goal has the same rows, so you can compare two goals line by line: `available`
   (the build has the operation at all), `configured` (what it needs is set up here), `authenticated`,
   `operation-ready`, `blocked` (what stops the goal here, and the one next action) and `unsupported` (what this
   build does not do), then a `live` row that says no live run has happened and lists the recorded blockers for one.
   The `authenticated` row stays `not checked` unless you ask for the check, which runs the same listing as step 3:
   `intune-iac catalog demo --check-signin azure`. On the sample, `inspect` is operation-ready; `discover` is blocked,
   and says why; `adopt` and `change` are blocked too, and `change` reads `against the modeled service only; no cloud
   route exists`. Below the goals the catalog lists the object kinds and families with their support stage, the saved
   projects it found in the folder with the command to resume each (typed from the folder where you ran `catalog`),
   and one next action per goal. `--goal` shows one goal only and `--json` prints the same facts as data.

   The next action for `discover` is the `capture` command. Do not run it now: it is the one command the catalog
   prints that would contact a real service (it sends a read token you supply to graph.microsoft.com, in GET
   requests only), and nothing in this guide needs it.

7. Open the workspace, the full-screen view of the store:

   ```sh
   intune-iac workbench workspace --root demo/store --service-root demo/service
   ```

   The Estate list shows the sample policy. Press Enter to select it (this opens the Inspector, tab 2). Press `3` for
   the Relationships tab: it draws the relationship map, a tree from the policy to what it targets (assignments, an
   exclusion, a filter) and what it configures (a scope tag, the setting). Up and Down move between nodes, Home
   follows an edge to its other end, Enter inspects a node, and `b` goes back. `?` lists every key, `a` lists the
   actions, and `:` opens a command line that accepts any `workbench` command name. Two of those names open read-only
   layers over the view you are in: `:catalog` shows the catalog of step 6 and `:workflow` shows the workflow map of
   step 8. Esc closes either, and no key in them changes anything. Press `q` to leave; the last read-only view is kept
   for the next start.

   If you have no terminal (a script, a pipe, a window smaller than 40 columns by 12 rows, or `TERM=dumb`), the same
   engine answers as plain text. This prints the relationships of the policy and then leaves:

   ```sh
   printf 'select 22222222-2222-4222-8222-222222222222\nrelationships\nquit\n' | intune-iac workbench workspace --root demo/store --service-root demo/service
   ```

8. Read the workflow map. It shows where one policy stands on its path from observation to maintenance, stage by
   stage. This prints it as plain text, writes nothing, and works without a terminal:

   ```sh
   intune-iac workbench workflow --root demo/store --policy 22222222-2222-4222-8222-222222222222 --service-root demo/service
   ```

   The first line is `[WORKFLOW]` and the policy. The stages come in a fixed order: observe, adopt, intent, propose,
   review, approve and execute, readback (with reconcile as a branch of it), record, observed after and maintain.
   Each stage carries one state word from a closed set (done, current, waiting, blocked, refused, unknown, not
   recorded, not applicable) with a mark, and the record it was read from (its `basis`). `@` marks the position, the
   last stage whose state is recorded. A stage with no record says `not recorded`; it never says that work has not
   started, and an unknown outcome is never drawn as done. On the sample the position is observe (`Position: observe`),
   because nothing else has been recorded for the policy yet. The later stages fill in when the policy is taken through
   the change route against the modeled service (`propose`, `review`, `execute` and `reconcile`), which
   `docs/WORKBENCH.md` describes and this quickstart does not walk. `--json` prints the same facts as data, and the
   text ends with `This view is read-only` and what it reads.

   In the workspace, with the policy selected as in step 7, press `:`, type `workflow` and press Enter. Up and Down move
   between stages, and the detail below the map follows the focused stage (its basis, the reason and the next step,
   where the product has one).
   Enter opens that stage's own view, Esc closes the layer and `b` goes back. The map needs a window of at least 60
   columns by 20 rows; below that the layer says so in one sentence, and the command above prints the same map.

9. Look at the engineering view. `engineering` shows engineering orchestration records, the tasks that an automated
   engineering loop dispatched and the state each reached, as plain read-only text:

   ```sh
   intune-iac engineering
   ```

   The records come from a directory that the loop's own `loopctl export` command writes, and that tool is not part of
   this archive. Without such a directory the command says `Engineering records are not configured` and what to pass,
   exits with status 0, and the rest of the product works as before. If whoever shared the build gave you one,
   `intune-iac engineering --records DIR` prints one entry per task (an identifier, a role and a state) and a closing
   line that counts the tasks by state; `--json` prints the same as data. It carries no prompts, results or free text,
   and it cannot dispatch, approve or cancel anything.

10. See what the product says it supports. `families` lists every policy, application and script family with its
    support disposition, read from `family-coverage.csv` and the integration manifest in this archive:

    ```sh
    intune-iac workbench families
    ```

    `"available": true` means both files were found. Every family other than the plain Windows Settings Catalog one
    is staged, review-only, reference-only or later.

11. Make the larger synthetic estate. `synthetic generate` writes it into a new folder; seed 42 is the default, so the
    identifiers are the same every time:

    ```sh
    intune-iac synthetic generate --output demo/estate --policies 3
    ```

    It prints one JSON record that holds `"synthetic": true`. You can build a workbench from it the way step 5 builds
    one from the sample export: give `workbench lab-create` the file `demo/estate/capture-estate.json` as its input,
    and one of the policy identifiers in it as the object.

    This estate has its own made-up tenant and lands inside `demo`, beside the first one. If you run `start demo` or
    `catalog demo` after this step, they list its exports and context as well, and the `discover` goal then says `Two
    tenants are named by the surveyed inputs; choose one.` That is expected: the two estates name different tenants.

12. Leave. Close the workspace with `q`, leave the virtual environment's folder as it is, and delete the `demo`
    folder when you are done with it; it holds only the sample outputs:

    ```sh
    rm -r demo
    ```

## Check a clean install end to end

To see the whole path work on a machine that has never held the product, run the demonstration script. It
unpacks the archive into a new folder, checks `SHA256SUMS`, makes a fresh virtual environment, installs only from the
folder of wheels with `--no-index`, runs the quickstart above without a terminal (every command in it except the
interactive workspace, which it replaces with the text variant of step 7), and prints one line for each step. Run it
from a folder that is not inside a git checkout, and give it a work folder that does not exist yet (a fourth
argument, the archive digest from the build receipt, makes it refuse a different archive):

```sh
bash scripts/demo-clean-install.sh /path/to/Intune_IaC_Plugin_0.9.0.zip /path/to/wheelhouse /path/to/new-work-folder
```

On a host whose Python has no `ensurepip`, add `--pip-wheel PATH`, the path of a pip wheel file (see
Troubleshooting). The script then makes the environment without pip, runs every pip command from that wheel, still
offline from the wheel folder, and prints the wheel's sha256 before it starts:

```sh
bash scripts/demo-clean-install.sh --pip-wheel /path/to/pip-24.0-py3-none-any.whl /path/to/Intune_IaC_Plugin_0.9.0.zip /path/to/wheelhouse /path/to/new-work-folder
```

The script exits 0 when every step passed, 1 when a step failed, 2 when it refused to run in a checkout, 3 when
the archive failed verification and 64 when it was called wrongly. It uses `python3` unless the `PYTHON` variable
names another CPython 3.12 with the `venv` module.

## Support limits

Read these before you rely on any result.

**Evidence.** Everything in this build is one of three kinds of evidence. SYNTHETIC means generated or bundled
sample data and a modeled stand-in for the service: it shows how the product behaves, and says nothing about any
real tenant. CAPTURE means pages that someone captured from the Microsoft Graph API with the `capture` command and
a read-only token they supplied; the product checks that the pages are consistent, but it cannot prove they came
from the tenant they claim. LABORATORY means a local run of real tooling in a controlled setup, not production.
No result in this build is production evidence. The sample data and the whole quickstart use synthetic and modeled
evidence only: nothing in them comes from a real tenant.

**No live write.** No live tenant, CI or cloud write exists in this build. No route sends a change to Microsoft
Graph, starts or changes a CI run, or writes to a cloud service: `doctor` reports `cloud_apply` as `unavailable` and
`live_qualified` as `false`, the maintenance commands (`propose`, `review`, `execute` and `reconcile`) run against
the modeled service only, and the catalog says the same for the `change` goal. `capture` can read a real tenant with a
read token you supply, and `signin collect` does the same with the Azure sign-in you already have, in both cases in
GET requests only. No such read is qualified for live use, none is part of this guide, and a capture is labelled
CAPTURE, never production. A sign-in that `signin status` or `catalog` finds is never permission for anything.

**What is covered.** The Windows Settings Catalog policy family is the only family carried end to end, and only as
local, reviewed, inactive candidates. Templates, endpoint security, applications and scripts are recognized, listed
(see `families`) and not carried through.

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

**Open gates.** One known defect in the provider is open: how it handles a malformed error response from the service
(gate G13 in `docs/EXTERNAL-GATES-R4.md`). The repair attempt was denied at its automatic review, the denial stands,
and there is no replacement provider and no workaround. It does not change what this guide asserts, because nothing
here runs against a real service. G01 to G12 in the same document name the real environments and owners that
qualification still needs (native Windows, a real tenant and identity, a protected CI platform, enrolled devices, an
independent security review and the owner's production decision); none is closed.

**The terminal.** The visual workspace needs a window of at least 40 columns by 12 rows. Below that it shows only the
session, the hazard and the prompt, never the body. The relationship map, the catalog layer and the workflow layer
each need at least 60 columns by 20 rows; in a smaller window they say that they need a larger one.

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

**Exit status.** 0 is a successful local result; `start`, `catalog` and `engineering` are reports and end with 0
whatever they find. 2 means blocked, partial or unavailable (read the printed reason), and is also what a usage error
returns. 3 means an invalid request or a failed operation. 4 means an output conflict or a held lock (use a new,
empty folder). 5 means missing dependencies. 130 means you interrupted the command.

**`python3 -m venv` fails.** Many Debian and Ubuntu hosts ship CPython without `ensurepip`, the module that puts pip
into a new environment, and `python3 -m venv .venv` then stops with "The virtual environment was not created
successfully because ensurepip is not available". It leaves a half-made `.venv` folder: delete it before you try
again. There are two ways round it.

The first is to install the package that holds `ensurepip`, `python3.12-venv`, with your system package manager
(`apt install python3.12-venv`; this needs administrator rights). Then run the install step again.

The second needs no administrator rights and no network: make the environment without pip, and run pip from a pip
wheel file. A pip wheel is a zip file that Python can run in place. Use any pip wheel you already hold: the one in the
`_bundled` folder inside `ensurepip` of another CPython installation that has it, or one fetched on a machine with
network access and carried across. It is read where it lies and nothing is copied. With the wheel folder of the
offline variant next to you:

```sh
python3 -m venv --without-pip .venv
.venv/bin/python /path/to/pip-24.0-py3-none-any.whl/pip --isolated install --no-index --find-links ./wheelhouse --require-hashes --only-binary :all: -r requirements-runtime-linux-x86_64-cp312.lock
```

The hash flags work exactly as in the install section; only the program that reads them is different. The
environment has no pip of its own afterwards, and nothing in this guide needs one. The demonstration script,
`scripts/demo-clean-install.sh`, does the same with `--pip-wheel PATH` (see "Check a clean install end to end") and
prints the wheel's sha256, which you can compare with the digest published for that pip release.

**A usage error (exit status 2).** The parser printed a usage line and something like `argument --tenant: invalid value
(the value is not shown)`. It never repeats what you typed, because a person can paste a secret where a name belongs.
Run the command with `--help` and compare.

**`invalid_request` (exit status 3).** The message is "Request failed validation or local I/O." A path does not exist
or cannot be read, a folder that must be new already exists (running `workbench init` twice on one store folder does
this), or a file failed validation. The message names nothing on purpose. Check each path with `ls` and give every
output a new folder.

**`output_conflict` (exit status 4).** The message is "Existing output cannot be safely replaced." The output folder
already holds earlier output. The result reads `failed_no_effect_verified`, which means nothing was changed. Use a
new, empty folder.

**`workbench_object_missing` (exit status 3).** The policy identifier you gave is not in the store. Copy the exact
identifier from the Estate list (the workbench never accepts a display name), and check that `--root` is the store you
built.

**`model_service_missing` (exit status 3).** The message is "Synthetic service evidence is incomplete, changed, or
outside the supported model." The folder given as `--service-root` is not an intact modeled service: it is missing,
incomplete or changed. Point it at the folder that `workbench lab-create` made.

**`capture_token_missing` (exit status 3).** `capture` reads a real tenant, so it needs a read token that you put in
the environment variable you name with `--token-env`; it takes the variable's name, never the token. Nothing in this
guide runs it. If you meant to stay offline, you are already in the right place.

**`BLOCKED` from `signin status` (exit status 2).** The reason code `cli_not_found`, as in `AZURE: BLOCKED (unknown:
cli_not_found)`, means the Azure CLI is not on the search path. Other reason codes name what did not match, and the
Why and Next step rows under the verdict say what to do (for example run `az account list --output json` yourself,
or sign in with `az login`). It is a report, it changes nothing, and it is the expected answer for the made-up sample
tenant.

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
pinned version. The pins are in the `wizard --journey` output (`pins`) and in `docs/OPERATING-PROFILE-R4.md`. The
quickstart needs neither tool.

**Nothing draws in the workspace.** Use a larger window, or run it under a real terminal rather than a pipe. With the
text fallback you type commands (`help` lists them) instead of pressing keys. If the catalog or the workflow layer
says it needs a larger window, widen the window to at least 60 columns by 20 rows, or print the same content without a
terminal with `intune-iac catalog demo` or the `workbench workflow` command of step 8.

## Reporting an issue

**The channel for sending a report is awaiting the owner's choice, so this guide names no address; until the owner
names one, give the report to the person who shared this build with you.**

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
