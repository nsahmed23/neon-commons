# Native offline qualification — 0.2

Date: 2026-09-30. Repository examined read-only: `intune-iac-plugin`.

**Result:** Atmos 1.199.0 and the Python literal resolver agree on all 11 exact-input fixtures: ten successful value comparisons and one expected type-conflict rejection. OpenTofu 1.10.0 parses the tested generated HCL and validates a provider-free fixture. Microsoft 365 provider schema and candidate validation remain **unqualified** because the native plugin did not start.

## Verified tools

| Tool | Verified release bytes | Verification |
|---|---|---|
| Atmos 1.199.0 Linux amd64 | `8e4b057f0cf38686c5eb61db57c8291027a22dfc4ce54a806dc83b34aa96757b` | Binary matches official SHA256SUMS and GitHub asset digest; release metadata contained no signature sidecar |
| OpenTofu 1.10.0 Linux amd64 ZIP | `ff8aebfd069f15f3f9ba7814444c8cae05428314c2ded0faedb9d040f6936cdb` | Matches official SHA256SUMS and GitHub asset digest; checksum GPG signature verifies with official key fingerprint `E3E6E43D84CB852EADB0051D0C0AF313E5FD9F80` |
| deploymenttheory/microsoft365 1.0.0 Linux amd64 ZIP | `412f6594404eacbbf61e11c289231a1089e6955e8fe80d081ee1aa6596da4281` | Matches official SHA256SUMS, GitHub digest and registry checksum; checksum signature verifies with registry-distributed key fingerprint `93C35A0678D1F851B477D95C2BC5232BA17AB08A` |

OpenTofu executable SHA256 is `0a9eda0f0898896969492504a6ce778f310675e8a1eb960434c26806cd252627`; provider executable SHA256 is `903774df6d165f10a0df2a013c2f69e921cfd2b9b4a2d8b1bddc03758a4cca61`. GPG verified signatures; independent certification of key-owner identity was not established.

An initial provider transfer returned truncated bytes despite curl exit 0. The checksum gate rejected it before execution. A second official download returned the expected 91,836,195 bytes and checksum. Both receipts are retained.

Official sources: [Atmos release](https://github.com/cloudposse/atmos/releases/tag/v1.199.0), [OpenTofu release](https://github.com/opentofu/opentofu/releases/tag/v1.10.0), [provider release](https://github.com/deploymenttheory/terraform-provider-microsoft365/releases/tag/v1.0.0), [provider registry download metadata](https://registry.terraform.io/v1/providers/deploymenttheory/microsoft365/1.0.0/download/linux/amd64).

## Atmos boundary and observed semantics

Commands used the verified native executable with `describe component leaf -s qualification --format json --process-functions=false --process-templates=false`. Fixtures were self-authored literal YAML without executable tags, functions, templates, auth/env declarations, providers, backends or hooks. No real repository stack was passed to native Atmos. The implementation path contains no HCL; its configured engine command is nonexistent.

Native and Python consumed the same prepared fixture directories. Runtime-only CLI configuration keys were removed before this shared run; one generated YAML alias was expanded into equivalent literal mappings. Original and prepared source hashes are both retained. Every source file remained unchanged across native execution.

| Fixtures | Native result matched by Python |
|---|---|
| `imports_ab`, `imports_ba` | Later import wins conflicts; nested maps retain nonconflicting entries; lists replace |
| `inherits_parent_a`, `inherits_parent_b` | Later inherited parent wins; implementation remains explicit `demo` |
| `scope_local`, `scope_override` | Local component values override root/type/parent; component overrides apply last |
| `empty_values`, `parent_to_child`, `child_to_override` | `""`, `0`, `false`, `null`, and `[]` overwrite; `{}` preserves an existing map's children |
| `null_shapes` | Scalar/list/map → null and null → scalar/list/map replace the prior value |
| `type_change` | String → list collision is rejected by native mergo; Python reports its bounded type-conflict blocker |

This qualifies **literal vars behavior for these cases**, not arbitrary Atmos behavior, stack identity, provenance completeness, list append/merge modes, commands, backends, provider lifecycle or tenant targeting.

The compared Python implementation SHA256 is `c655817c058703973d5df96d1e776b618cfcde80c8a1aacb882c5818847efb95`.

## OpenTofu and provider checks

- Provider-free `init -backend=false -input=false -no-color` and `validate -json` both exited 0; validation reported zero errors and warnings.
- `fmt -check` parsed copied supported/Azure example HCL and the current candidate's `main.tf.txt` copied as `main.tf`. Exit 3 identifies formatting differences, not a provider-validity result. Original repository files were unchanged.
- Provider installation from an explicit filesystem mirror with `init -backend=false -input=false -get=false` exited 0. OpenTofu labeled the local mirror installation unauthenticated and created a Linux-only local lock file; the archive and checksum signature had separately been verified before installation.
- `providers schema -json` and candidate `validate -json` exited 1 with an **Unrecognized remote plugin message** startup diagnostic. No provider schema was obtained. An independent probe establishes that the managed base runtime denies AF_UNIX socket creation, which prevents ordinary local plugin IPC; the generic native diagnostic does not itself establish the exact cause. Schema and resource configuration validity remain unknown.

No plan, apply, import, cloud access, Graph request or model call was performed. The inactive candidate guard and all authorization flags remain unchanged.

## Isolation and receipt export

Native children received a complete environment allowlist without credentials. HOME was not reassigned: the pinned Atmos homedir fallback called a self-authored `getent` adapter that returned a fixture directory. Explicit XDG directories and OpenTofu CLI configuration also pointed to fixture paths. No filesystem sandbox is claimed: namespace/chroot isolation was unavailable. Seccomp denied all sockets for Atmos/general OpenTofu checks and every non-AF_UNIX socket family for the provider attempt; the base runtime independently denied AF_UNIX. No sockets were inherited by native children.

Copy **only** `offline-qualification-0.2-receipts/safe-export/` plus this report into a distributed source archive. The export contains 76 small evidence/source files (approximately 107 KB), including normalized native receipts, original/prepared Atmos fixtures, comparison code and an explicit `export-manifest.json`. It excludes downloaded binaries/archives, public key files, keyrings, full runtime configuration output, network headers, caches and installed provider trees.

Direct evidence hashes:

| Evidence file | SHA256 |
|---|---|
| `atmos-python-comparison.json` | `0edfa195123d169258f7f636fc030e3a0c7ff96d9bde96405e328eaef211c423` |
| `python-fixtures-native-source-manifest.json` | `f2ffdc09ff53f99e85be4d95f1a105744dbaae2a332483e228d7f9bf87d0e014` |
| `provider-candidate-source-manifest.json` | `48f67679ad2ec725b5e12fac18118bc11715518c74220a9b15e216dcea8b2a7b` |

The comparison and source-manifest files record each exact YAML path/hash and each fixture's source fingerprint. The candidate manifest binds the exact three copied candidate files; qualification does not silently transfer to later source changes.
