# Supplemental 0.5 security records

This bounded supplement records 13 repaired findings, seven open qualification gaps, and 25 threat/invariant/control/test/evidence rows from existing implementation reviews and receipts. It does not perform a new product test run or certify enterprise production readiness. Acceptance remains `BLOCKED_FOR_ENTERPRISE_PRODUCTION`.

- `findings-ledger.json`: qualitative impact, exact regression references, hashed evidence, and remaining qualification gates.
- `threat-control-matrix.json`: controls and evidence classes linked to each finding, additional verified controls, and open gaps.
- `artifact-leak-scan.json`: explicit point-in-time inventory, bounds, rules, redacted match hashes, assessments, and scanner limits.
- `validation.json`: JSON parsing and referenced evidence hash checks; no test or service calls.
- `build_security_records.py`: local reproducible record builder and bounded heuristic scanner. It writes only this directory.

The scan covered 221 explicitly scoped new artifacts/source files with no skipped or unstable files. Its 20 matches were 17 synthetic fixture literals, two public schema descriptions, and one marker-word reference. All four initially unresolved candidates were manually assessed by exact path and match hash; none remains unresolved. No real credential or canary payload leakage was confirmed. The heuristic scan cannot establish absence of secrets; no real-secret corpus, environment values, credential stores, home directories, or process memory was read.

Evidence distinguishes recorded response fixtures, real local cryptography, native OpenTofu sealed-plan behavior, real local socketpair/stdlib HTTP parsing, and live services. The positive socketpair tests reached and asserted the native local path; they do not establish TLS, Microsoft service, or provider RPC qualification. Same-account compromise, private authority-store modification, and a compromised shared Python interpreter remain outside the protected host boundary. Native provider lifecycle and live service/integration gates remain open. The owner's final integrated run and packaging receipts are separate release evidence, not inferred from historical or in-progress receipts here.
