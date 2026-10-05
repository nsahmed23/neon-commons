# Native hosts and evaluation contracts

## Scope and evidence

No host was installed, no native Claude/Codex validation ran, no paid model call was made, and no provider/tenant operation ran. This document is a qualification plan. The Python schema/model tests are not host tests.

Use the current official OpenAI plugin and Claude plugin/eval documentation listed in `sources/REFERENCES.md`, plus the pinned local implementation recorded by the original dossier. OpenAI documentation describes portable root `plugin.json` and a legacy `.codex-plugin/plugin.json` fallback; the original audited Plugin Eval resolver at `openai/plugins` commit `5fd93af4cd0c623e020d0cc7e9ce178b4ac1f70f` recognizes the legacy path. That prior code evidence is not a fresh installation test in this pass. Avoid claims of plugin-aware analysis if the resolver reports generic directory.

Keep a single source manifest and, where the chosen host really requires it, a generated compatibility artifact with an equality/precedence check. Do not silently add a second conflicting manifest to improve an analyzer grade. Resolve actual inline OpenAI-settings precedence against overlays. Test relative files, activation, optional dependencies and invocation on the specific installed host version. No templates in this pack are asserted installed.

The pinned Plugin Eval benchmark implementation uses schemaVersion2 and `runner.type=codex-cli`; older Responses-oriented prose does not supersede implementation. Distribution version and package version must both be recorded. Verify config loading through an isolated no-model validation path or an inspected unit stub before real runs. Do not assume a `--dry-run` flag prevents model invocation: the pinned benchmark text states real CLI execution and warns there is no simulated dry-run mode. Never run it merely to discover the schema.

Anthropic `claude plugin eval` is a separate case/grader/harness contract. Its documentation distinguishes static plugin validation from paid behavioral runs, and documents shell/scaffold/platform constraints. Check the exact current CLI help in an approved environment, keeping paid runs and report publication disabled unless authorized. Do not infer WSL tests are native Windows tests, or that a scaffold script/MCP server inherits the agent's sandbox.

## Platform gates

1. **Native Windows generation:** approved Python/runtime; actual PowerShell version recorded. Run quoting/metacharacter/JSON encoding/native exit tests against a harmless argument-echo child, no cloud binaries. Validate path casing, reserved names, long paths, exclusive locks, replace/rename and interrupted writes.
2. **Linux Bash:** actual Bash/runtime version; same decoded argv vectors, EOF/cancel, Unicode and no-color behavior; correct pipeline exit handling. Test assignment-like executable rejection and an absent executable not yielding success.
3. **Terminal/host:** plain and TTY modes, narrow width, Ctrl-C, EOF, back/edit, stale resume, missing prerequisites, user-file conflicts; external operation log shows zero unexpected auth/download/installation. Test plugin discovery and expected skill loads with synthetic fixtures.
4. **Native package validation:** host tool's actual validation output and package/path checks. Installation/load success is separate from schema validity and from task benefit.

## Four comparison arms

A: no domain skill. B: selected upstream composition. C: proposed skill with the same tools as A/B. D: proposed skill plus new helpers/enforcement. Declare any tool or permission asymmetry; do not attribute D-C gains to prose. Run Claude and Codex experiments separately with identical case versions, budgets and explicit model versions within a comparison. Isolate homes and plugin stores; do not silently inherit live tokens, unrelated skills or cached private context.

Before every run, check the intended plugin is absent/available and whether the expected skill was actually loaded. Keep source configuration common, keep golden answers and grader code outside the candidate's read/write surface, and keep result logs protected. Reinitialize fixtures per run. Repeat failures with fresh contexts; an initial three repetitions is not a rare-failure reliability estimate.

Cases must include supported adoption completion, incomplete capture, malformed setting, lost exclusion/filter, duplicate references, wrong tenant/stack/backend/cloud, mutated digest/key, unsupported raw canary, early/partial resume, emit-only, malformed ownership manifest, forbidden executable token and simple question. Score useful actual files plus invariants; a bot that refuses all tasks fails usefulness. Do not use exact prose matching as a substitute for correct outcomes.

Capture issued and executed operations using the external runner/transport, not final agent self-report. Attempted actions require observable tool requests; do not demand private thought transcripts. Observe real argv, paths written, network/auth attempts, process exit and artifacts. Critical wrong-target mutation, secret disclosure, fabricated evidence, boundary escape and grader tampering block release rather than being averaged away.

Results: pass/fail/not-run/blocked/unsupported/skipped/harness-error per case with denominators; model/harness versions, real input/output/cached tokens only if emitted, static token estimates separately, latency, list-price calculations separately from billed costs. Grader-sensitivity mutations must make expected assertions fail before model comparisons count. Missing usage is null, not zero.

All these gates remain not-run here. The full dsoxlab manifest and broader family qualification remain separate outstanding work; neither should displace repair of the nine first-slice findings.
