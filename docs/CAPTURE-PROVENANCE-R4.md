# Capture provenance and tool context

A typed `LaboratoryGraphReader` now writes `synthetic: true` in its export and
`source_is_synthetic: true` in context and receipt. Its sealed observation remains
`graph_reader_laboratory`, with no authenticated live-service or execution
claim. The live reader explicitly supplies false only from its existing typed
native identity route; serialized flags cannot construct that capability.

Low-level `capture()` preserves its existing caller-declared default. Injecting
a callable is not proof of either real service access or synthetic origin. The
optional boolean records the caller's assertion; the receipt always retains
`tenant_assurance: caller_asserted`, `source_authenticity_verified: false` and
`execution_authorized: false`. The typed laboratory reader supplies its known
classification explicitly. Ordinary imported bytes remain unverified evidence.

New context files omit provider, Atmos and OpenTofu version values because the
capture process did not observe those tools. The receipt states that the context
contains proposed emit-only target labels, not an observed toolchain. Actual
execution tool versions and bytes belong to the separately verified native
worker manifest and receipt.

The observation importer accepts matching explicit boolean provenance and
requires a laboratory receipt marker when the export says synthetic. It reuses
the same field mapper through `production.normalize_observation`; raw bytes and
labels are not rewritten. `production.normalize` retains its existing
non-synthetic candidate gate. Both routes retain mapping, reference, ownership
and provider qualification blockers and grant no execution authority. Unsupported
settings IDs, types, assignments and unknown fields do not become supported.

Historical captures remain byte-exact. Their synthetic-false/template-version
labels are a retained provenance finding; a new correctly labeled capture does
not repair them. Earlier typed laboratory receipts still establish only their
explicit laboratory scope. Root's first attempted transport inference broke the
legacy capture route and remains under `capture-provenance/attempt01`; the final
repair preserves that route and changes the typed producer. The 100 named tests
in attempt03 cover capture, raw import, retry, typed reader, persistent jobs and
production mapping. Their scope overlaps existing tests and is not a new release
total. Independent review and exact-package qualification remain separate.
