# Runnable Intune IaC plugin implementation

Historical plan for the first runnable local plugin. Tasks below describe that implementation phase; current capabilities, unresolved engineering and acceptance gates are maintained in [PRODUCT-STATUS.md](PRODUCT-STATUS.md). Release verification records observed checks.

The existing Knowledge Catalog investigation and action/CLM contracts are the design brief. This build adds an executable product around the repaired preservation core. It does not turn unqualified provider or cloud behavior into a passing result.

1. Runtime engine: strict bounded input loading; direct repaired normalization/generation/oracle calls; file ownership; post-write verification; explicit supported synthetic mode and review-only production boundary.
2. Semantic graph: typed scoped identities, provenance, coverage, policy/setting/assignment/reference edges, explicit Atmos declarations and unresolved expressions; fixed read query vocabulary.
3. Action runner: fixed registry, typed parameters, preview without dispatch, exclusive target lock, receipts bound to bytes, unknown-outcome handling. No arbitrary shell dispatcher.
4. Interactive terminal wizard: source/context/output intake, inspection, selected policy, mapping blockers, generation/review, back/edit/save/resume with byte fingerprint invalidation. Noninteractive equivalent for automation.
5. CLM adapter: real HTTP protocol integration with strict candidate/distribution checks, bounded evidence, configured model identity and advisory-only results. Missing service reports unavailable. Protocol tests do not claim inference quality.
6. Host integration: root Agent Plugins manifest, legacy Codex compatibility manifest, Claude packaging where supported, runnable skill, CLI, JSON-RPC stdio MCP tools. Runtime package excludes evaluation answers and research dossiers.
7. Independent review, existing regressions, negative integration cases, clean runtime extraction, installation and usage instructions.

## Shared Python interfaces
- `intune_iac.io.load_json(path)` strict object/array JSON; `digest(value)` canonical JSON SHA256; `file_sha(path)` bytes; `write_json(path,value)` atomic 0600 JSON; `AppError(code, message)` safe errors.
- `intune_iac.engine.inspect_source(input_path, context_path)` returns a safe dict: status (`ready` or `blocked`), policy_id, tenant_id, normalized, blockers, source_sha256, context_sha256. It calls the independent oracle. Raw unsupported data never goes into public output.
- `intune_iac.engine.generate(input_path, context_path, output_path)` returns safe status/output/path count/digests/preservation result; active generation stays within the qualified bounded mapping.
- `intune_iac.graph.build_graph(input_path, context_path=None, atmos_root=None)` -> JSON dict. `query_graph(graph, query, subject=None)` -> safe JSON. Agent documents exact query names.
- `intune_iac.runner.preview(action, parameters, state_dir)` and `run(action, parameters, state_dir)` -> dict. Registry actions `inspect`, `generate`, `graph_build`, `graph_query`; file path parameters only. Root wires CLI.
- `intune_iac.wizard.run_wizard(session_path, input_path=None, context_path=None, output_path=None, input_fn=input, output_fn=print)` -> dict; owns only wizard state and calls runner. No cloud execution or model authority persists.
- `intune_iac.judge.assess(config_path, claim, evidence)` -> dict; exact CLI config documented by implementer. Advisory only, deterministic checks independent.

Python 3.11+, stdlib + existing PyYAML/jsonschema/python-hcl2. No import-time execution. Each module owns its named test file. Tests exercise real implementations with literal negative expectations; network doubled only at HTTP boundary. All paths below are relative to the build checkout.

## Ownership
Root: `io.py`, `engine.py`, CLI/MCP, package manifests, runtime packaging, integration, documentation.
Graph agent: `graph.py`, `atmos.py`, `plugin_tests/test_graph.py`, graph docs.
Runner agent: `runner.py`, `plugin_tests/test_runner.py`, runner docs.
Wizard agent: `wizard.py`, `plugin_tests/test_wizard.py`, wizard docs.
CLM agent: `judge.py`, `plugin_tests/test_judge.py`, CLM config example and docs.

Production Graph capture, provider import/apply, Atmos effective execution, native Windows and learned-model behavior remain separately qualified capabilities. The runtime must report that fact, without describing unavailable adapters as operational.
