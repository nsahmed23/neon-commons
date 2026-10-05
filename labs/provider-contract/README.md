# Selected-provider source characterization

The baseline profiles compile **unchanged selected files** from Deployment Theory microsoft365 1.0.0 (`1718c946b3ae111bb44c7c1d925b3e35b708cb0a`) with its unchanged `go.mod` and `go.sum`. The explicit `patched` completion profile applies the hash-bound source and dependency changes listed in `completion-manifest.json`. The tests use the real Terraform Framework validator, state mapper, plan modifier, JSON normalizer, custom GET helper and Kiota JSON writer. An optional profile adds the actual provider settings constructor and Microsoft Graph SDK models.

The HTTP transport is an in-memory Go `RoundTripper`. It never dials a socket or authenticates. The fake adapter only converts Kiota request information to an HTTP request. Every other adapter operation remains unavailable. This isolates the custom helper's behavior; it is not a simulation of Microsoft service semantics.

`TestKnownHazard...` tests deliberately assert observed defects in the pinned upstream implementation. **A green characterization suite means these defects reproduced. It does not mean the provider is safe.** The receipt always has `production_qualified: false`.

## Prerequisites

- Linux amd64, reviewed Go 1.26.8 distribution. The runner pins the executable hash, records its version and uses a clean environment. The explicit `--toolchain-profile legacy-1.25.8` exists only for offline historical reproduction; current advisory evidence excludes that old toolchain from the updated candidate profile.
- A pristine source tree matching `source-manifest.json`. The source release also contains those exact files under `research/provider-qualification/raw/provider/`; that directory can be supplied as `--upstream`.
- Go module dependencies acquired and verified against the selected profile's exact module sums. The patched profile uses the updated sums in `completion/go.sum`; baseline profiles use the original sums. Acquisition is separate. The qualification runner disables ambient Go configuration and sets `GOPROXY=off`, `GOSUMDB=off`, `GOTOOLCHAIN=local`, `GOTELEMETRY=off` and `CGO_ENABLED=0`.
- A fresh output directory outside the plugin, provider source and module cache. Existing outputs are never reused.

```bash
python scripts/qualify-provider-contract.py \
  --upstream /absolute/provider-source \
  --go /absolute/go1.26.8/bin/go \
  --module-cache /absolute/verified-go-module-cache \
  --output /absolute/fresh-provider-contract-result
```

Add `--with-sdk` to compile the full SDK models package and actual settings constructor. This is expensive: the initial ordinary-GC attempt was killed while compiling the SDK models under this host's 8 GiB memory limit. The runner uses one compiler worker, `GOGC=20` and `GOMEMLIMIT=5GiB`, with a 600-second whole-process deadline. Failure to build is a failed receipt, not a skipped/pass outcome.

The helper profiles have no provider initialization, Terraform RPC, tenant operation, HCL schema validation, import, plan or apply. The separate in-process lifecycle profile below calls actual resource methods. Neither profile is a protected execution adapter. Output contains selected source files, Go build cache and test evidence; synthetic fixtures only. The lab assumes a trusted, cooperative local filesystem and dependency cache. It is not a sandbox for untrusted Go installations, cache entries or edited tests.

## Separate repair and extracted-schema profiles

Use `--patch-profile original` to run the desired GET/pagination behavior tests
against the unchanged provider (expected failure). Use `--patch-profile patched`
to stage the hash-bound local helper candidate and run those same tests. The
candidate's strict paging/body limits and affected DELETE caller are documented in
`research/provider-qualification/patches/README.md`. This does not replace any
registry binary or promote provider qualification.

Use `--schema` for the exact AST-extracted `SettingsCatalogJsonResource.Schema`
method. The utility retains the original method bytes and supplies a minimal inert
receiver; all selected helper files remain unchanged. It runs the Framework's
schema implementation checks and selected field validators/defaults. It does not
instantiate the full resource, validate HCL through the provider, run RPC, or
establish default/validator sequencing in a real Terraform plan. Neither lifecycle
methods nor credentials exist in this profile. The receipt records the source and
method hashes and the exact extraction byte/line boundaries.

Profiles run separately. `--build-cache /absolute/trusted-existing-go-cache` can
reuse an existing local build cache; otherwise each output gets a fresh cache.
Go test result caching is always disabled (`-count=1`).

## 2026-10-02 completion candidate

The new `completion/` source tree and `completion-manifest.json` repair the selected resource path directly against the pristine v1.0.0 pin. They are separate from the historical GET-only candidate in `patched/`; do not apply both patches together. New evidence and explicit unsupported profiles are in `research/provider-qualification/completion-20261002/REPORT.md`.

`qualify-provider-contract.py --completion-profile original|patched` executes actual selected source with the real SDK writer and configured Kiota adapter against in-memory responses. `--full-build` additionally stages the complete pinned build-input inventory and compiles the real provider; it is not a lifecycle qualification flag. All receipts retain `production_qualified: false`.

`native_validate.py` performs only native schema RPC and HCL configuration validation through pinned OpenTofu 1.10.0. It never requests configure, import, read, plan or apply and supplies no cloud credentials. A local plugin socket may require explicit execution permission in restricted environments. The published baseline and local candidate binaries must be labeled separately; a baseline native schema result cannot qualify a patched binary.

## 2026-10-04 actual resource and dependency repair

Add `--completion-profile patched --inprocess-lifecycle` to stage the complete
pinned source plus the explicit patch and call the actual selected resource's
Schema, Configure, ImportState, Read, Create, Update and Delete methods. The
independent stateful `RoundTripper` observes outgoing requests and models remote
IDs, settings and assignments. Missing identities, denied/lost assignment
responses, incomplete observations, invalid counts and recovery have negative
controls. The same harness is retained for before/after comparison.

The repair records only known identity and local timeout configuration before a
separate assignment operation. Successful complete readback supplies remote
state. Missing create identity requires reconciliation; it never authorizes a
blind create retry. Bad requests do not establish deletion, and missing child
collections do not establish disappearance of their parent policy.

The October dependency patch is distinct from the inherited binary. It updates
the affected declared modules and their required transitive resolutions, and
uses Go 1.26.8. Exact module graphs, advisory queries, license records and
reachability analysis accompany the epoch evidence. Modules present only in
development/tool graphs are still inventoried; absence from the tested Linux
CGO-disabled provider main graph is not a universal safety claim.

The full build and in-process profile have a 1,800-second outer bound, a single
compiler worker and a 5 GiB soft Go memory target. Failed compilation and earlier
shorter-deadline attempts remain failures. Resource tests have their own finite
deadline; no Go test result cache is used. A saved build cache is an explicit
replay prerequisite for a warm build, not a cold-start measurement.

In-process Read equality does not establish second-plan convergence. Provider
RPC, authentication, real service semantics and live identity/approval/backend
integration remain separate gates. Never relabel the original binary as
containing newer source changes; bind a rebuilt binary to its exact source and
toolchain receipt before invoking the native RPC harness.
