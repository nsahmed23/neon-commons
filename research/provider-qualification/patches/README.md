# Local upstream repair candidate

`0001-bound-custom-graph-GET.patch` targets exactly provider 1.0.0 commit
`1718c946b3ae111bb44c7c1d925b3e35b708cb0a` and one source file. Original and candidate
SHA-256 values are in `../../../labs/provider-contract/patch-manifest.json`.
The complete modified source and MPL-2.0 license are in
`../../../labs/provider-contract/patched/`.

The patch repairs demonstrated transport/envelope defects. The runner verifies
the original source before staging and verifies both hashes before substitution.
It never edits the acquired provider checkout or an installed provider binary.

Local support restrictions are explicit: public Graph HTTPS endpoint, unchanged
escaped collection path and host across continuations, at most 128 pages, at most
4 MiB per successful response and 32 MiB combined input, no redirects, 30-second
HTTP client timeout per request. These limits are not claims about Microsoft's
service limits. Entire returned query strings remain intact. Initial configured
queries are encoded explicitly because the upstream URL template did not expand
them. Settings and assignments suffixes require collection envelopes; generic
non-collection object responses remain admitted.

The shared `makeRequest` helper is also called by the custom DELETE helper; its
new status/body/redirect handling affects that caller too. No DELETE operation
was run. A full provider fork would need all affected caller tests, adapter
middleware integration, complete assignment pagination, setting/state equivalence,
schema/RPC and import/plan/service qualification. No merge/replace or atomicity
semantics are inferred from this patch.

Reproduce before/after with the same runner arguments as the lab README, plus
`--patch-profile original` (expected failure) or `--patch-profile patched`
(expected passing desired-behavior tests). Do not combine these with `--with-sdk`.
Baseline characterization and patch regressions intentionally assert different
behavior and are reported separately.
