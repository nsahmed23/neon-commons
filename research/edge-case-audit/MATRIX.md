# Edge cases and evaluation coverage

Scope: engineering release 0.3.1. No finite suite covers every edge case. This matrix distinguishes executable local checks from missing environment/model/service qualification. Test files under plugin_tests/ are the anchors; core preservation tests also run from evaluations/.

| Failure class | Concrete checks / anchors | Remaining boundary |
|---|---|---|
| JSON ambiguity and limits | Escaped duplicate keys, depth64/65, unsafe integers, exponent overflow, lone surrogates; test_edge_input_audit | Arbitrary-precision decimals and all Graph polymorphs unsupported |
| Capture completeness | Missing first/next page, loops, wrong origin, denied/failed collection, duplicate observations, count contradictions; test_capture*, test_production, repaired core tests | Authenticity, freshness and transactional consistency across live requests |
| Graph identity and semantics | Rehashed duplicate edge ID, coverage contradiction/removal/wrong subject, unknown declaration promotion; test_edge_input_audit, test_graph* | Authenticated source/reference ownership and broader ontology support |
| Preservation oracle | Boolean/integer substitutions in normalized and emitted evidence, duplicate generated JSON keys, YAML false/zero; test_oracle_edge_types, test_edge_input_audit, test_preservation_audit | Actual selected-provider request/state equivalence and broader settings |
| File safety | Symlink/path traversal, ownership conflicts, restrictive new modes, interrupted writes; test_generated_permissions, test_runner, test_workflow*, test_release_audit | Hostile same-user filesystem races, power loss, Windows ACLs |
| Progress and locking | Missing/tampered receipts, changed input/cohort/stack, saved frontier, malformed state, replaced/in-place/symlink lock ownership; test_edge_workflow_audit, test_workflow | Native host-driven recovery and multi-process/distributed behavior |
| Plan effect denominator | Prior/planned resources/outputs, typed values, imports, replacement, unknown/sensitive/deferred effects; test_execution | Native binary-plan provenance, full engine/provider matrix |
| Recovery | Six journal write boundaries, independent facet expectations, retained locks, replay refusal; test_edge_workflow_audit, test_reconciliation | Service-side partial update, ambiguous remote readback and remote leases |
| Target evidence | Structured identity/backend mutations, wrong endpoint, missing evidence, secret-safe result; test_target | Authentication, effective principal/federation and state writer observation |
| Shell and host | Argument roundtrip and Linux CLI/PTY/MCP checks; test_cli*, test_mcp_audit, repository qualification | Native Codex/Claude registration, Windows/PowerShell |
| Dependency/release integrity | Exact wheel bytes, malformed metadata, malicious archives, clean extraction, deterministic rebuild; test_dependencies, test_ci_contract, test_release_audit | Publisher authentication, full supply-chain assurance, organization CI run |
| Test result honesty | Empty/skip/expected failure/unexpected success, multiple failed subtests, skipped subtest, positive success; test_verifier_contract | Deliberately omitted test discovery or false test assertions still require review |
| Judge protocol | Malformed/oversized/timeout responses, synthetic probabilities, strict advisory output; test_judge | Learned quality, model identity, calibration, prompt-injection robustness and latency |

## Distinct evaluation gates

1. **Deterministic local behavior:** executed full suite and independently specified mutations. An unchanged positive control must still pass; a fresh digest must not conceal changed semantics. Red evidence is retained.
2. **Structural plugin evaluation:** static Plugin Eval, with a separate report. Packaging policy metadata, source size and style heuristics are not behavioral accuracy. Real publisher policy URLs cannot be fabricated to improve a score.
3. **Native agent tasks:** still unrun. Required scenarios include correct routing, ambiguous intake, unsupported content, unexpected tool failure, interruption/resume, preserved exclusions and refusal of unapproved actions. Judge task success against resulting artifacts and forbidden effects, not the agent's self-report.
4. **Learned judge quality:** still unrun. Freeze independently labeled supported/contradicted/insufficient examples and hold out entities/templates to limit leakage. Include contradictory sources, confident unsupported claims, missing relationships, mixed conjuncts, source-injected instructions, reordered distractors and paraphrases. Report false-support rate, abstention/coverage, selective risk by threshold, confidence intervals and worst-slice performance. Measure cold/warm latency and failures against pinned serving identities and hardware. Do not turn a probability into execution authority.
5. **Native provider/service acceptance:** still unrun for the complete shipped path. Required experiments include complete assignment refresh, empty/omitted/merge semantics, import plus ordinary/refresh-only no-change, fail-before/fail-after/lost-response, concurrent writers and readback recovery in a named authorized tenant.

## Findings and review

Input and workflow reviewers built counterexamples before repair. They then cross-reviewed the graph, workflow, verifier and oracle changes. No blocking issue remained in this bounded change scope. Root's complete verifier passed 624/624. This is 27 additional methods over the previous release; subtests, repeated scoped runs and original failing cases are not added to that total.

The goal remains open. Native host/service/model gates are reported as unrun, never converted into skipped tests and then called green.
