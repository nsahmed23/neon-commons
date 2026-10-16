# Validation CI and operational handoff

`.github/workflows/validate.yml` is an implemented validation-only workflow for an engineering candidate. It has been parsed and exercised locally at its contract and shell boundaries. The published 0.8.0 source has two failed GitHub runs with zero jobs; the R4 read-only reassessment below preserves that contrary platform evidence. The repaired R4 definition has not yet passed a GitHub-hosted run. A green validation job does not approve production use.

## Declared CI support

The workflow targets GitHub.com or GitHub Enterprise Cloud hosted `ubuntu-24.04` runners, Linux x86_64, and CPython **3.12.14**. It uses Node 24 actions, whose published minimum Actions Runner version is 2.327.1. The selected artifact action is not supported on GitHub Enterprise Server. A GHES or self-hosted adaptation needs separate platform and artifact qualification; this file does not claim it.

| Action | Version label | Immutable commit selected from upstream |
|---|---|---|
| `actions/checkout` | v6.1.0 | `d23441a48e516b6c34aea4fa41551a30e30af803` |
| `actions/setup-python` | v7.0.0 | `5fda3b95a4ea91299a34e894583c3862153e4b97` |
| `actions/upload-artifact` | v6.0.0 | `b7c566a772e6b6bfb58ed0dc250532a479d7789f` |

The pins were verified using remote tag resolution and independent shallow clones of the primary repositories. The source ledger records hashes and inspected metadata/source paths. This is not a claim of publisher-signature verification or a complete audit of each bundled JavaScript dependency. The upstream Python distribution manifest lists the exact Ubuntu 24.04 x64 build; this workstream did not download or execute that distribution.

## What runs

1. Check out the triggering revision without retained checkout credentials and select the exact Python version.
2. Assert the supported platform. Download only the ten hash-locked runtime wheels, check their exact filenames/bytes/metadata, then install offline into a fresh virtual environment with `--require-hashes` and run `pip check`.
3. Run the full plugin and repaired-core verifier. Both the exit status and the structured receipt must pass. Any failure, error, skip, missing count, wrong count type or incomplete core suite fails the gate.
4. Run the actual synthetic CLI, repository and Linux terminal qualification scripts.
5. Build runtime/source ZIPs from the explicitly reviewed file inventory into a fresh directory outside the checkout.
6. Verify archive receipt hashes, ZIP paths/types/duplicates/CRC and exact member hash coverage, then check that every member the runtime archive shares with the source archive has the same bytes in both, before extracting into a new directory. Each archive's own `SHA256SUMS` and `BUILD-IDENTITY.json` are left out of that comparison because each describes its own archive, so the two differ by design. The two identity records are checked against each other and against their archives instead: both archives must hold one; the records must agree on `built_at`, `commit`, `dirty`, `product_version`, `schema_version` and `tree`, and what they agree on must be a value the builder writes (`product_version` the version in the receipt, `dirty` false, `commit` and `tree` 40 lowercase hexadecimal characters, `schema_version` `build-identity/1`, `built_at` a UTC time written `YYYY-MM-DDTHH:MM:SSZ`); each record's `companion` must name the other archive as it is (its kind, and the digest the builder always writes there, which is required: the source's `content_sha256` in the runtime record and the runtime ZIP's `archive_sha256` in the source record; any other digest it carries must be right too); and each record's `archive_kind`, `file_count` and `content_sha256` must match its own archive. A refusal names the field and nothing is extracted.
7. Run the full verifier against the extracted source and `doctor` against the extracted runtime, then run the extracted source's builder with `--check-only` and compare the runtime and source content digests it reports with the `content_sha256` in each original archive's `BUILD-IDENTITY.json`. That shows the source archive holds everything the runtime archive was made from. The ZIPs are not rebuilt: their identity records name the commit and the build time, and the builder makes archives only from a known, clean Git checkout.
8. Upload only candidate archives and named verification directories, including available failure evidence, for seven days. Hidden files and overwrite are disabled.

The job has only `contents: read`. No cloud secrets, OIDC token permission, login action, provider execution, tenant capture, import, apply, deploy environment, pull-request comment or release publication is configured. Checkout/setup may use GitHub's ephemeral platform token for repository/runtime retrieval under that read-only permission; it is not exported as a shell credential, and checkout persistence is disabled. The artifact action uses the platform's artifact service. These platform transfers are not a cloud deployment.

The events are pull requests targeting `main`, pushes to `main`, and manual dispatch. Local checks share no deployment concurrency group; newer validation of the same ref cancels an older run. All run steps use Bash with `-euo pipefail`. No check uses `continue-on-error` or a success-forcing fallback. The always-run artifact step cannot turn an earlier failed check into a successful job.

## Repository administrator handoff

Before enabling this file, the repository owner must review its branch names, hosted-runner availability, action allowlist, artifact access/retention policy and the named validation status. Configure branch protection or a ruleset to require the validation job for the actual protected branch, require independent review of workflow/dependency/release-inventory changes, and select the accountable support owner. These repository settings have not been configured by this work.

Keep untrusted pull requests on isolated hosted runners without production credentials. Do not switch the trigger to `pull_request_target` or route fork code through a privileged `workflow_run` consumer. A candidate produced from pull-request code is untrusted input for any future deployment pipeline; validation artifacts are never approval tokens.

For the first authorized GitHub run, retain the commit SHA, run URL, selected action SHAs, runner image details, interpreter version, dependency verification and the full verifier/CLI/extraction results. Verify both failure handling and a successful run. That observed host execution is still an open acceptance gate here.

## Failure and recovery procedure

| Failure | Required operator action |
|---|---|
| Wheel hash, inventory or metadata mismatch | Stop installation. Inspect the selected distribution and upstream source, then make a separately reviewed lock change if justified. Do not delete the hash gate or substitute unhashed installation. |
| Test/CLI/PTY failure | Preserve the failing receipt and logs, reproduce against the exact revision, repair the cause and rerun all affected gates. Do not reclassify a skip or expected failure as complete qualification. |
| Archive/path/member hash mismatch | Preserve the candidate and receipt for investigation. Rebuild from a reviewed clean revision into a fresh directory; never overwrite a mismatching candidate in place. |
| Extracted tests or the content-digest comparison fail | Treat the package as unreleasable. A differing digest means the source archive does not hold what the archive was made from: check inventory completeness, missing fixtures/dependencies and generated files before changing expected outputs. |
| Artifact upload fails | The job remains failed. Preserve available workflow logs and rerun after resolving the artifact-service or policy issue; do not infer a release from local test success alone. |
| Interrupted or cancelled validation | It grants no release status. Start a fresh run for the intended revision; no tenant/state reconciliation is needed because this workflow performs no tenant/provider operations. |

If an artifact or log unexpectedly contains restricted data, follow the organization's incident and deletion/retention process and review the test input or logging path that introduced it. The current scripts use synthetic/local fixtures. Hash manifests and filename filters do not classify arbitrary repository content for secrets.

## Updating dependencies and actions

Review exact upstream changes before replacing a pin. Confirm the commit belongs to the primary action repository, update the source ledger and contract tests, and rerun YAML/shell validation and the full workflow on the declared platform. For Python/platform changes, acquire a separately reviewed wheel set; the Linux CPython 3.12 lock is not a universal requirements file. The hosted runner image, Python distribution service, bootstrap pip and action dependency tree remain infrastructure trust dependencies even though application wheel bytes are locked.

Do not add cloud access to this validation job. A future deployment pipeline needs its own reviewed identity/target binding, protected approval, exact binary-plan provenance, native state and distributed operation locks, durable effect receipts and recovery evidence. Enterprise goal gates E03–E05, E08–E10 remain open until their own evidence exists.

Local evidence and source identities: `research/enterprise-ci/README.md` and `source-ledger.json`.

## R4 observed workflow admission failure and local repair

Read-only GitHub evidence on2026-10-07 identified runs37572241575 and37570928891
for exact source289ee9477372825aad848f4482cf681c2ff43b02. Both completed with
`failure`, zerojobs and zerocheckruns. The public run annotation states
`(Line:27,Col:16): Unrecognized named-value: runner ... runner.temp`. The old
job-level `env` used a runner context before it was available. Earlier local
YAML parsing and contract tests did not establish GitHub workflow admission.

The local repair moves CI_ROOT initialization into the first runner-executed
Bash step via GITHUB_ENV. It requires an absolute RUNNER_TEMP and rejects CR/LF
before appending a line. Existing read-only permissions, fixed action pins,
strict verification gates, artifact scope and failure propagation remain.
Name-driven test mutations preserve their original gate targets after the new
step; a new negative rejects the previously invalid job-level context.

Raw APIresponses, public annotationHTML, exact beforebytes, test commands and
repair receipts are in `work/evidence/epoch-20261007-r4/external-gates/`. This
repairs source locally; actual admission and runner execution of final bytes
remain a required GitHub gate. Source and handoff branches were observed
unprotected; read permissions reported by a connector do not authorize changing
branch controls, deployments, protected environments or production identities.

The 0.9.0 candidate also prepares the already admitted libsodium validator
explicitly. `scripts/prepare-ci-validator.py --package EXACT_DEB --output NEW_DIR`
checks the original161290-byte Ubuntu package SHA-256
`74d6f8fbd65f7f71b6f4f4223bef5fb57c1c14cd4e9ce788ead2b88e8c3ee236` before
reading its payload, then checks the unchanged355040-byte library pin
`fe00408090ea084504d7cb0130af56a22554fe299034b864551b65a64ca8a7b5`.
It reads only the selected regular library/copyright members, executes no
maintainer script, installs no system package and records the extraction tool.
The workflow supplies the verified path to test fixtures through GITHUB_ENV.
This is local dependency preparation, not new library or hosted-run approval;
missing/wrong package bytes remain a failing prerequisite. The hosted image,
network availability and actual final CI run still require their own evidence.
