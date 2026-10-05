# Host, capture, and CLM audit — v0.2.0

Audit baseline: `77682f84022232569418e6ff4e678f2cf06246de`. Reviewed `intune_iac/mcp.py`, `capture.py`, `judge.py`, related tests/docs, runtime manifest files and the release builder. Pinned CLM source reviewed locally at `bb42c6c5bf914fd449bed2f6ca65be80602cb1f7`, especially `src/clm/schema.py`, `engine.py`, `server.py`, and `embedder.py`.

The local integrations had reproducible correctness gaps despite the existing passing tests. They are repaired in the working checkout. The repairs do not establish native host loading, live Graph collection, CLM factual accuracy or production adoption readiness.

## Reproduced findings and repairs

| ID | Severity | Baseline behavior | Repair and evidence |
| --- | --- | --- | --- |
| H01 | High | An MCP `initialize` request with `protocolVersion: []` or `{}` raises an uncaught `TypeError` at set membership. The server terminates instead of returning a protocol error and processing subsequent requests. | Validate negotiation metadata before changing state or checking protocol membership. `plugin_tests/test_mcp_audit.py` sends each malformed request followed by a ping and requires an error plus a successful ping. |
| H02 | Medium | MCP accepts missing protocol/client/capability metadata, serves tools without `notifications/initialized`, and permits repeated initialization. UTF-16-BE messages can be accepted because the generic JSON loader detects encoding. | Explicit UTF-8 decoding, required initialization metadata, separate new/negotiated/ready states, operation gating until notification, and duplicate initialization rejection. Updated existing client fixtures and the repository qualification script to use the valid handshake. |
| H03 | Medium | Capture reports `captured`/complete for duplicate assignment UUIDs differing only by letter case. String equality handles these as separate observations. | Compare policy and assignment UUID identity canonically while preserving original bytes. Opaque setting IDs remain case-sensitive. Regression verifies both partial coverage and unchanged source records. |
| H04 | Medium | Capture reports complete when `@odata.count` disagrees with total rows or is an invalid type, when page counts contradict one another, or when a record has no usable ID. | Validate nonempty string IDs, integer/nonnegative counts, and every declared count against the terminal chain total. The original bodies remain intact in raw/export evidence. Positive controls cover correct multi-page totals and distinct opaque setting IDs. |
| H05 | Medium, delegated | Source-release traversal includes arbitrary untracked regular files; exclusions alone do not make the source archive a reviewed inventory. Runtime packaging is more narrowly selected. | Reported to the root agent, who owns `scripts/build-release.py` remediation and tests. No duplicate patch made here. |

H03/H04 are collector coverage errors. The downstream production mapper/oracle already blocked the tested count/case contradictions; this audit did not observe an active-IaC or cloud execution bypass.

## Verification

- Nine new regression methods were executed against the actual v0.2 source loaded from its Git commit. MCP produced **9 assertion failures and 2 application TypeErrors across subtests**; capture produced **10 assertion failures and zero errors**. These are baseline defects, not fixed results. Counts are subtest failures, not nine independent test executions.
- After repair, the targeted MCP, CLI, capture, and existing judge suite ran **50 tests with zero failures/errors/skips**.
- The actual repository qualification script ran **7 successful CLI checks**, including the repaired MCP handshake. It used constructed local fixtures, no provider calls and no cloud calls.
- Baseline receipts and full logs: `/workspace/scratch/26b6d364cfda/host-audit-evidence/mcp-baseline.json`, `mcp-baseline.txt`, `capture-baseline.json`, `capture-baseline.txt`, and `fixed-tests.txt`.
- Repository subprocess receipt: `/workspace/scratch/26b6d364cfda/host-audit-evidence/repository-qualification/result.json`.

These checks verify concrete error handling and coverage behavior. They are not native MCP-host installation or a behavioral model evaluation.

## CLM result

No additional reproducible judge-adapter defect was established during this review. The implementation matches the pinned System One request structure, state/instruction composition, candidate order and candidate-relative confidence formula. The adapter rejects malformed probabilities, model aliases, unsafe configured endpoints, unsupported token-bound recipes and failed requests; its result remains advisory and cannot authorize execution. The 17 existing judge tests exercise actual loopback HTTP with synthetic distributions, not learned inference.

Important remaining product work:

1. Run held-out Intune/Atmos evidence cases against an actual immutable serving deployment. Measure false support, false contradiction, abstention coverage, prompt-injection resistance, latency and resource use. The 0.8 probability / 0.2 margin gates are not calibrated.
2. Verify the effective encoder revision, pooling, tokenizer recipe, head generation and input limits. Current response aliases cannot authenticate deployed model weights; a local checkpoint hash alone does not attest a remote service.
3. Qualify maximum request duration and recovery under a stalled service. Current docs correctly describe socket timeouts, not a guaranteed end-to-end deadline. Capture likewise explicitly documents a guard between requests rather than asynchronous cancellation. These are operational limitations, not newly hidden claims.
4. Integrate any reliable advisory judgments into the intended workflow and evaluation corpus while retaining independent deterministic preservation and authorization gates. A functioning HTTP adapter is not a trained or measured domain judge.

## Host and distribution boundary

The three host manifests have aligned names/version and the runtime skill/launcher paths are present. Source packaging and runtime packaging are separate. Neither manifest inspection nor Python subprocess tests prove a host successfully loads or uses this skill. Native Codex/Claude installation, native Windows behavior, host policy delivery, publisher listing/legal URLs and behavioral evaluation remain separate release gates. Missing public URLs must not be replaced with invented values to improve a static score.

## Primary protocol references

- MCP lifecycle, 2025-06-18: https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle
- MCP stdio transport, 2025-06-18: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- MCP tools, 2025-06-18: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- Pinned CLM source: https://github.com/Contrastive-LM/CLM/tree/bb42c6c5bf914fd449bed2f6ca65be80602cb1f7

The MCP references were checked during this audit. Source review supports protocol shape, not a claim that any model inference or live Graph request occurred.

## Independent preservation cross-review

After the host repairs, the root requested a cross-review of the separate preservation agent's changes. No preservation code was edited by this reviewer.

Two concrete findings were sent to the preservation author for repair:

- The synthetic reference path still accepted duplicate assignment UUIDs differing only by letter case. Changing the second assignment ID to the first assignment ID in uppercase returned `ready`, `preservation_verified:true`, `offline_mapping_complete:true`, and no blockers. Distinct target groups prevented the existing target-tuple check from catching the duplicate source identity. Both producer and oracle shared case-sensitive identity comparison. This was observed before that author's follow-up repair.
- The new production lineage oracle scanned every record location for every source node. With 500/1,000/2,000 extra minimal unselected policies, observed oracle times were 0.079/0.141/0.488 seconds, compared with normalization times 0.008/0.014/0.025 seconds. The last input was only about 100 KB. Dictionary-based ancestor lookup was recommended to avoid quadratic work; a source-node limit was also recommended because per-node lineage expands compact JSON substantially. These are local measurements, not a formal performance benchmark.

Independent positive checks compared **59 observation destination values** directly with their originating source nodes. Seven hostile unsupported-field insertions covered policy, setting wrapper, setting instance, choice value, assignment, target and page body. Names containing `/` and `~` and nested canary values remained absent from normalized artifacts; all cases blocked candidate generation and were accepted by the independent oracle as correctly blocked results. No incorrect destination pointer or unsupported raw-value leak was found in those probes. This is bounded evidence, not exhaustive proof over Graph polymorphism.
