# Integrated repair change map

This working copy derives from the supplied original Appendix B archive and its correction pack. The source archives remain unchanged. Current verification counts are recorded in verification/result-summary.json, not copied from historical receipts.

## Implementation changes

- Real pinned jsonschema, PyYAML and HCL parser dependencies with a preflight check. Missing dependencies are blocked harness outcomes.
- Correction schemas enforce strict GUID lengths; valid authentication object/null changes return controlled mismatches; preview command identifiers use a registry.
- Pipeline validation binds collection roots and owners, requires a complete page chain, rejects ambiguous references and malformed/unsupported settings, and applies a populated capability map.
- Provider configuration retains setting IDs and omits the validated wrapper discriminator. Source, configuration and actual provider request/state remain distinct contracts.
- Unknown raw fields and sensitive values are excluded from emitted observations/reviews. Field accounting records rules, destinations and restricted-retention findings.
- The independent checker derives identity, digests, mapped values, targeting and field dispositions independently, and inspects actual generated import/HCL structures. The CLI runs it before writes.
- File ownership errors become conflicts; output is staged separately. Source raw-byte/canonical digests are recorded in the generated project.
- The receipt/resume layer rereads artifact bytes and dependency evidence. Early/partial sessions remain constrained by verified prerequisites and saved progress. Approval matching remains a consistency check rather than authentic authorization.

## Test versioning

The supplied original 33 assertions remain historical reproduction material under corrections/regressions. The integrated suite reuses them, updating only the F07 schema lookup to the explicitly versioned v2 fingerprint/index contract. Integrated workflow tests exercise actual persistence and routing; graph-edge checks alone do not establish correctness.

Original golden files are regenerated only after the independent checker accepts the repaired output. Positive examples and adversarial mutations remain separate so unconditional refusal cannot count as successful preservation.

## Qualification boundaries

These repairs do not establish service assignment replace/merge semantics, refresh pagination, provider no-update roundtrips or failure recovery across separate policy/assignment requests. No provider process, state import, cloud call, native host installation, native PowerShell qualification or paid behavioral benchmark is part of the offline verification receipt.

Existing correction-model and numbered original verification logs are historical. The top-level verification/result-summary.json identifies the current integrated result and its scope.

The original absent/null/empty description test was updated to require restricted retention for invalid values rather than echoing them. The input remains unchanged; field-kind evidence distinguishes null, array and empty string. The CLI and independent raw parser share the exact-integer ±(2^53−1) canonical boundary.

Final adversarial review also closed artifact-level gaps: raw receipts are mandatory for byte-backed output checks; import/lifecycle/command/Atmos structures and module placement are checked explicitly; output reruns reject extra files and symlinks; receipt inspection rejects duplicate kinds, corrupt lockfiles and unmanifested component inputs. Concurrent store creation uses an exclusive local lock. Complete nine-milestone workflow positives and late prerequisite mutations supplement early/partial cases.
