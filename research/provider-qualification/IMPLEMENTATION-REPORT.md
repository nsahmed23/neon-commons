# Selected provider engineering and qualification report

Task 1 of the enterprise execution plan is implemented as a source harness, a concrete upstream repair candidate, regression evidence, an extracted-schema qualification path and a pinned raw-source ledger. **The installed/registry provider is unchanged, and the enterprise production gate remains open.**

## What was executed

| Check | Observed result | Scope |
|---|---|---|
| Unchanged provider/SDK characterization | 27 top-level Go tests passed; zero failures or skips | Real provider validator, state mapper, normalizer, plan modifier, settings constructor, SDK Entity/choice serializers and Kiota writer; in-memory GET transport |
| Desired paging/HTTP behavior against original | 2 control cases passed, 12 top-level cases failed; 28 failed Go nodes including subtests; zero skips | Reproduced concrete upstream defects; these are expected failing regressions, not repaired outcomes |
| Same desired behavior against local source patch | 14 top-level cases passed; 30 Go nodes including subtests; zero failures or skips | Modified actual custom GET source compiled with unchanged selected dependencies; no service calls |
| Exact extracted resource Schema | 6 top-level Go tests passed; zero failures or skips | Framework `ValidateImplementation`, required/computed field contracts, bounded settings validators, description limit and filter default/validation contracts |
| Python qualification-runner guards | 9 unittest cases passed | Failure/empty/truncated/skip handling; unsafe source paths; source hashes; compiler pin; exact patch-base/candidate staging; owned descendant cleanup |
| Patch applicability | `git apply --check` exited 0 | Exact pristine provider commit; no upstream checkout changes |

Primary machine receipt: `evidence/before-after.json`. Each profile keeps its full result and stdout/stderr beneath `evidence/`. A passing characterization test intentionally reproduces known defects; it does not count as a safe provider behavior. Go test subtest nodes and top-level cases are reported separately to avoid inflating coverage.

## Material findings and implemented repair

The real provider's settings helper accepted an initial HTTP 403 as a successful body. Its state mapper then accepted that JSON error object as the value of `settings`. More seriously, a 403 on a later page became a successful **truncated settings collection**, because the error JSON had neither `value` nor `nextLink` and the helper did not inspect HTTP status. These findings are executed source behavior, not deductions from comments.

The same helper attempted foreign and repeated continuations without its own origin/loop bounds. It could ignore a continuation if the first page lacked `value`. Its initial `$expand=children` query was also dropped: the URI template did not include query expansion. The in-memory adapter and transport proved these request-construction/envelope behaviors without credentials or network sockets.

The reviewable MPL-2.0 patch is `patches/0001-bound-custom-graph-GET.patch`; its complete source is `../../labs/provider-contract/patched/get_request.go`. It now:

- Rejects non-2xx statuses, error envelopes, malformed/duplicate envelope keys, null or missing collection values, and invalid continuation types without returning partial results.
- Admits only the initial public Graph HTTPS host and exact escaped collection path. Foreign, relative, user-info, alternate-port and fragment-bearing continuations are refused before request conversion.
- Preserves the complete returned continuation query and explicitly encodes initial query parameters.
- Rejects repeated continuations and caps the chain at 128 pages, 4 MiB per response and 32 MiB of combined response input.
- Rejects redirects, applies a 30-second per-request HTTP timeout, validates the converted request type, and omits response bodies from errors.

Those are conservative local support restrictions, not Microsoft service-limit claims. The shared `makeRequest` function also serves the custom DELETE helper; that affected caller has **not** been qualified. The patch still uses a default HTTP client rather than the configured adapter's client/middleware. A deployable fork needs broader caller tests and an approved adapter design. No patch was published, installed or executed against Microsoft Graph.

The repaired boundary is transport and collection-envelope handling. It does not validate every returned item, reject duplicate resource identities, establish count consistency, or prove collection completeness at the service. The broad 2xx acceptance rule also needs endpoint-specific qualification before release.

## Settings and assignment contract evidence

The actual selected constructor receives `id` in the shared typed model but does not set it on the SDK setting. The real SDK serialization test confirms the outgoing setting omits that ID. The SDK itself preserves explicitly assigned IDs; the omission occurs in the provider constructor. The constructor also omits null template references and empty children, while the SDK choice-value constructor supplies its discriminator. The real writer distinguishes nil fields from non-nil empty arrays.

The state mapper retains response wrappers and array order, and malformed JSON can retain the old settings string. Plan normalization does not reconcile those differences. These are reasons to keep the current plugin's production candidates inactive. Renumbering settings, stripping observed fields, or weakening the oracle would hide the issue.

The full pinned assignments read chain was inspected from provider `Read` through generated SDK `Get` to Kiota `Send`: the provider consumes one response's `.GetValue()` and no inspected layer follows the assignment continuation. Settings pagination is therefore not evidence of assignment pagination. Assignment construction's null/unknown-to-empty and invalid-target skipping paths are acquired as raw code but were not executed by this bounded harness. Service replacement-versus-merge, empty/omitted semantics and assignment request outcomes remain unqualified.

The lifecycle's policy PUT, assignment POST and later read are separate operations with early returns. The patch does not make them atomic. `../../labs/provider-contract/service-qualification.json` names the remaining fail-before/fail-after/lost-response/readback cases and their required evidence. No synthetic service response is claimed to establish Microsoft's behavior.

## Extracted Schema assurance

Importing the full resource would pull `internal/client`, stable and beta SDK roots, and acceptance/testing dependencies through `resource_test_helper.go`, which is compiled as an ordinary Go source file. This is substantially broader than invoking the Schema method.

The extraction utility uses Go's AST to identify the exact `Schema` declaration, preserves its original bytes, verifies it does not read receiver state, and supplies a minimal inert receiver. It copies unchanged helper files and executes real Framework checks. Method SHA-256 is `75306e588e66045ad501265832e7af317c421c7e7eed6ab0dcefb264b219d5dd`; source and byte/line ranges are in `schema-extraction.json` and the profile receipt.

The observed filter contract is specific: the schema default produces the all-zero filter GUID, while explicit configuration of that value is rejected by its validators. Include/exclude modes require a filter ID. This does **not** establish the Framework's complete default/validator ordering through a real provider plan. No full resource, HCL decoding, native provider RPC, import or no-change plan ran.

## Acquisition, integrity and failed attempts

The full provider tree was cloned at v1.0.0, resolving to `1718c946b3ae111bb44c7c1d925b3e35b708cb0a`. The beta SDK is v0.165.0 at `95df3921a4dd9a40c65dd24b26b96988bb1191d0`; Kiota JSON writer is v1.1.4 at `f3bc194a238ea40d19288b8a4966afff69bc0307`. The ledger records the other exact module source identities, hashes, source URLs and licenses. Raw selected code is retained with its upstream license. Provider source is MPL-2.0; Microsoft SDK/Kiota sources are MIT.

Go 1.25.8 linux/amd64 was acquired from the official Go distribution and checked against the official download metadata SHA-256 (`ceb5e041bbc3893846bd1614d76cb4681c91dadee579426cf21a63f2d7e03be6`). The runner pins the Go executable hash and records the version. Dependencies were acquired separately using the provider's unchanged `go.mod`/`go.sum`; actual qualification runs disable module downloads, toolchain auto-download, telemetry and cgo, and receive no inherited cloud credential environment.

The first offline run correctly failed for absent dependencies. An initial SDK compilation was killed while compiling the large models package under the host's 8 GiB cgroup limit; the failed log remains. A one-worker low-GC retry succeeded, and the 27-case baseline also passed from a fresh build cache. The optional whole-module `go mod verify` attempt remained blocked because unused Azure modules from the full provider graph were not acquired (`GOPROXY=off`); it is not reported as an all-dependency verification pass. Two exploratory commands were initially launched from a directory without a Go module, failed before compilation, and were rerun from the correct staging module; these setup mistakes are not provider defects.

The standalone harness assumes a trusted, cooperative filesystem, Go toolchain and module/build cache. It is not a sandbox for arbitrary Go installations, cache entries or modified tests. Inputs used here are synthetic. Original source verification and patched staged-source hashes are separate receipt fields.

Independent review found that the runner skipped process-group cleanup when its group leader had already exited, even if a descendant retained its pipes. A regression against the exact pre-fix runner reproduced a continuing child heartbeat after the deadline. The repair always cleans the owned process group and closes both pipe handles. All nine runner tests then passed with resource warnings promoted to errors; a separate reviewer reproduced the stopped heartbeat. `evidence/runner-cleanup.json`, `descendant-cleanup-red.log` and `runner-green.log` preserve this evidence. The existing Go profile receipts identify the pre-cleanup runner hash; this runner-only correction does not alter the provider source or Go assertions. Host PID virtualization made an initial `/proc/<Popen.pid>` check invalid, so that probe was replaced with actual child output and is not the closure oracle.

## Additional source requested during execution

`DIAGNOSTIC-SOURCE-REVIEW.md` reviews `powerstacks-corp/intune-advanced-troubleshooting` at `68e04d3374f93d5895d66fc28581f25e1e250fdf`. Useful contributions are falsifiable hypotheses, UTC correlation, independent device/service signals and explicit missing evidence. The collector needs structured denial/truncation status, native exit-code handling, immutable bundles, restricted retention and hashes before it can be an enterprise adapter. No repository license file was present at the inspected pin; no code was copied and no collector/decompiler was executed.

## Remaining release gates

E02 remains partial. The smallest safe plugin change is **no promotion of the production mapper**: keep its existing inactive candidate and qualification blocker. This work supplies the actual source repair and repeatable evidence needed to qualify a future provider fork/release. Remaining gates are full native provider schema/HCL/RPC validation; complete assignment refresh; request/state round-trip equivalence; protected target/authentication and execution; service assignment semantics and partial-outcome recovery; and an authorized existing-policy import with ordinary and refresh-only no-change plans. The native host socket restriction was not bypassed.

Task code is confined to its assigned paths. No commits, publication, tenant actions or production mapper edits were performed by this worker. Root owns integration, independent review and the full suite.
