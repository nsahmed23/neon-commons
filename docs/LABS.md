# Native Atmos and state-locking labs

Open-source Atmos labs exist and are useful for this workflow. This source release
includes two executable local exercises and a source audit explaining what was
reused. Use the **source archive** for the scripts, fixtures, tests and research.
The runtime archive contains this guide but excludes lab tools and research.

## Run the native adoption lab

In the validation Python environment, with the qualified Linux amd64 binaries:

```sh
python scripts/qualify-adoption-lab.py \
  --atmos /absolute/path/to/atmos \
  --tofu /absolute/path/to/tofu \
  --output /absolute/path/to/new-adoption-run
```

The runner accepts only the pinned Atmos 1.199.0 and OpenTofu 1.10.0 binary hashes
and the reviewed fixture bytes. It needs Linux with libseccomp, creates a fresh
directory, uses a clean child environment and denies networking in native child
processes. It executes actual init, plan, import and apply commands against its
own local state. It cannot target a supplied repository or cloud backend.

Read `labs/atmos-adoption/README.md` for the detailed exercise and
`result.json` in the run directory for the assertion results. Command logs and
artifact hashes remain beside that receipt, including synthetic state and plans.

The exercise separates these identities:

| Identity | Evidence |
|---|---|
| Physical manifest | `stacks/deploy/dev.yaml` |
| Logical stack | Native Atmos resolution of `dev` |
| Component instance | Stack-selected policy component |
| Implementation | Catalog metadata and the Terraform module path |
| Workspace and state | Native workspace, local backend, lineage and serial |
| Existing objects | IDs and attributes captured before adoption |
| Desired targeting | Synthetic include/exclude values in a built-in resource |

The local state transfer retains the original state, then checks no-change plans
and original identities. A separate identity-only import demonstrates native
import behavior. Adding input after that bare-ID import must reveal a change;
it cannot stand in for a provider that reconstructs real policy settings.

Configuration change detection is not service drift detection. The lab does not
simulate Microsoft Graph, validate Intune request/state serialization, or qualify
the plugin's inactive production candidate. Its lab-only execution harness is
separate from the product's six fixed local action adapters.

## Replay the upstream locking checks

Acquire the pinned catalog and use a separate Python environment containing
pytest 8.4.2:

```sh
git clone https://github.com/stephrobert/terraform-dsoxlab-training
git -C terraform-dsoxlab-training checkout 86b69d2292485d179698f5b9bf648a29f935e216
python scripts/qualify-locking-lab.py \
  --upstream /absolute/path/to/terraform-dsoxlab-training \
  --tofu /absolute/path/to/tofu \
  --pytest-python /absolute/path/to/pytest-venv/bin/python \
  --output /absolute/path/to/new-locking-run
```

The runner checks the exact source and executable hashes before using them. It
supplies an independently authored local solution and adapts the fixture's
Terraform version requirement to the tested OpenTofu version. Eight unchanged
upstream behavior tests are selected. The S3 documentation assertion is explicitly
deselected; no remote backend is exercised. This is a test replay, not a dsoxlab
CLI or Terraform 1.15 qualification. It has a clean environment and fixed reviewed
inputs, and does not claim the adoption runner's seccomp isolation.

## Research and acceptance limits

- `research/terraform-catalog/README.md`: all 88 actual lab entries, automated
  plaintext-content scan, selected deeper reviews, encrypted solutions and two
  reproduced checker limitations. Static inventory is not 88 executed labs.
- `research/atmos-resources/README.md`: pinned Atmos, test-helpers and tfmigrate
  sources, licensing, current-versus-installed version differences and reuse decisions.
- `research/lab-workflow-audit.md`: reproduced product defects.
- `docs/PRODUCT-STATUS.md`: remaining production engineering and qualification.

No-change is necessary but insufficient: retain the pre-operation object IDs and
values, inspect structured plan changes, bind the exact executed plan and target,
and preserve state concurrency protections. A stale plan alone does not prove
which plan was applied, and a newly rediscovered object with the same name does
not prove preservation of the original object.
