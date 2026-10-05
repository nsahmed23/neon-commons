# Observe state locking with an actual OpenTofu process

This replay uses the plaintext tests from Stéphane Robert's
[Terraform dsoxlab training](https://github.com/stephrobert/terraform-dsoxlab-training/tree/86b69d2292485d179698f5b9bf648a29f935e216/labs/state/state-locking),
commit `86b69d2292485d179698f5b9bf648a29f935e216`. The upstream material is
licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
The replay preserves the upstream Python test and helper bytes, checks their
SHA-256 hashes before execution, and supplies an independently authored local
solution. It neither accesses nor decrypts the upstream reference solutions.

The upstream fixtures require Terraform `>=1.15.0`; this replay deliberately
changes that constraint to OpenTofu `=1.10.0`, using its built-in `terraform_data`
resource, local backend and a `sleep 20` observation timer. It measures the
observations first, writes them as outputs, then lets the original tests
repeat the experiment. That is an OpenTofu adaptation, not proof of execution
under Terraform 1.15 or through the dsoxlab CLI.

## Run

Use a reviewed checkout at the commit above, the previously qualified Linux
amd64 OpenTofu 1.10.0 executable, and a separate Python environment with
`pytest==8.4.2` installed. The script rejects a different binary hash and changed
upstream inputs. It requires Linux and GNU `timeout`.

```bash
python scripts/qualify-locking-lab.py \
  --upstream /absolute/path/terraform-dsoxlab-training \
  --tofu /absolute/path/tofu \
  --pytest-python /absolute/path/test-venv/bin/python \
  --output /absolute/path/new-locking-run
```

The output must be a new directory outside the plugin and upstream checkouts;
symlink traversal is rejected. Existing output is preserved. All state is
created beneath that directory. The verified executable is copied into this
private directory and checked again before use, so an update of the caller's
original binary cannot silently change later commands. Child commands use a clean environment, an
empty provider mirror and no inherited credentials. Each native CLI call has a
60-second timeout with a five-second termination grace period. The full pytest
invocation has a 150-second deadline. This is not an operating-system or network
sandbox; execute only the pinned sources and binary accepted by the runner.
If the top-level upstream pytest process is canceled, its separate child
sessions can continue until their 60-second timeout. Immediate cleanup of all
upstream descendants is not established. The runner does clean up the direct
measurement processes that it owns when a measurement fails or is interrupted.

The measurement pass and the upstream tests create, replace and destroy only
local `terraform_data` state. The runner and upstream test kill their own
replacement apply process groups to produce a stale lock-file scenario. The
provisioner only sleeps. No cloud or external provider is involved.

## What is checked

- A live local backend lock rejects a second plan and apply.
- Reads and the deliberately unsafe `plan -lock=false` bypass behave as observed;
  bypass is a negative-control experiment, not an execution recommendation.
- A one-second lock timeout waits and then fails while the lock remains held.
- The lock file follows the configured state path and records the CLI version.
- An abruptly killed apply leaves a file, but the operating-system lock is
  released; the next plan succeeds and removes the leftover file.
- Re-applying converges and the subsequent plan returns the no-change exit code.

Eight upstream behavioral tests are selected. The ninth, `test_backend_s3`, is
explicitly deselected because it compares static answers with Terraform S3
documentation; no S3 operation is performed and those answers must not be
reported as observed OpenTofu or Azure behavior.

`receipt.json`, `measurements.json`, `measurement-commands.json`, `upstream-pytest.json` and
`upstream-junit.xml` record actual results and deviations. A failure stays a
failure in the receipt. This lab qualifies local locking behavior; it does not
qualify Azure backend leases, the plugin's action locks, provider mutation
recovery, Atmos, Intune, or a production adoption flow.
