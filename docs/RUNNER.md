# Fixed local action runner

`intune_iac.runner.preview(action, parameters, state_dir)` inspects bytes and returns a JSON-safe proposal without dispatching an adapter or writing files. `run(action, parameters, state_dir)` creates a fresh byte-bound proposal and executes one of the six local adapters. A preview is informational and is not persisted authorization. A caller that resumes a saved workflow must compare its saved evidence fingerprints with a new preview; `run` independently rechecks its own bound evidence immediately before dispatch and after execution.

| Action | Required parameters | Optional parameters | Adapter and scope |
| --- | --- | --- | --- |
| `inspect` | `input`, `context` | — | `engine.inspect_source`; reads capture/context and independently verifies preservation |
| `generate` | `input`, `context`, `output` | — | `engine.generate`; generates or verifies an owned local project |
| `graph_build` | `input`, `output` | `context`, `atmos_root` | `graph.build_graph`; writes a new graph file, refusing existing files |
| `graph_query` | `graph`, `query` | `subject` | `graph.query_graph`; reads a stored graph |
| `repository_inspect` | `root` | — | Discovers literal Atmos stack/component choices and evidence |
| `repository_resolve` | `root`, `stack`, `component` | — | Resolves the supported literal subset and returns a value-free structural report |

All supplied parameter values are nonempty strings. Unknown/missing parameters, arbitrary command/code fields, unsupported query names, symlinked paths, and overlapping read/write scopes are rejected. Graph queries are exactly `policies`, `assignments`, `why-setting`, `impact`, `dependencies`, and `placement`. An Atmos root binds the byte hashes of its complete local file closure, limited to 4,096 files/32 MiB. State must be outside that closure, outside the generated target, and must not use an input file as a directory.

There is no shell, subprocess, model inference, installation, provider, Atmos effective execution, or cloud dispatch. Reserved unavailable adapters are `cloud_apply`, `cloud_import`, `native_windows`, `atmos_execute`, `provider_apply`, and `assignment_update`. Other unregistered names return `unknown_action`.

Repository actions bind the resolver's bounded source inventory (configuration, stack YAML, and recognized component HCL/lock files), rather than arbitrary repository contents. Their state directory must be outside the repository. They re-inventory before and after dispatch so additions, deletions, and edits to relevant source files change evidence. The standalone `repository` CLI and MCP tools are read-only and write no receipts; using the runner additionally persists attempt/result receipts.

```python
from intune_iac.runner import preview, run

parameters = {
    "input": "/project/capture.json",
    "context": "/project/context.json",
    "output": "/project/generated",
}
proposal = preview("generate", parameters, "/project/runner-state")
result = run("generate", parameters, "/project/runner-state")
```

Preview returns `status`, `action`, and `proposal` when ready. The proposal includes the stable action/adapter version, parameter digest, exact source byte fingerprints, target, read/write scopes, and proposal ID. A visible existing target lock returns `needs_review`; unavailable adapters return `unavailable`; invalid input returns `rejected` with a fixed safe error.

A run returns `action`, `proposal_id`, `operation_id`, `status`, and `receipt_paths`. Successful execution adds the adapter's JSON-safe `result`. Inspection may successfully verify a capture whose inner result is `blocked`; this does not authorize execution. The outer `succeeded_verified` describes the local adapter and its checked postconditions.

Before dispatch, the runner atomically creates a 0600 lock named `.intune-runner-lock-<canonical-target-hash>` beside the output target. The lock identity is the resolved output path, so another state directory cannot evade it. Target parents may be created during `run`, never during preview. The runner does not steal or expire a lock. Read-only actions need no output lock and use separate unique receipt IDs.

The runner writes separate `<operation-id>.attempt.json` and `<operation-id>.result.json` records. It rereads the attempt before dispatch and the successful result before releasing its lock. Receipts bind the action/adapter, parameter digest, evidence hashes, output target, and checked postconditions. They omit raw capture contents, adapter output, arbitrary parameter text, traceback, and exception messages. Directory evidence records contain relative file names and hashes. Filesystem paths and object names are not anonymized. Result verification rereads the engine manifest and every declared file, rejects unexpected files/symlinks, compares source/context byte hashes, and requires the engine's independent preservation check. Graph output is reread and checked against its byte digest.

| Status | Meaning |
| --- | --- |
| `rejected` | Invalid input, a pre-dispatch failure, or a failed read action |
| `unavailable` | Explicitly unavailable adapter; no dispatch |
| `needs_review` | Existing target lock prevents dispatch |
| `succeeded_verified` | Local result and declared postconditions verified |
| `failed_no_effect_verified` | Engine reported an ownership conflict and an independent full target snapshot proved unchanged |
| `outcome_unknown` | A write was dispatched but execution, evidence recheck, persistence, or postcondition verification failed; target lock retained |

An interruption leaves a `running` attempt and its target lock; interruption before attempt persistence can leave only the lock. The runner does not silently replay either case. An error after a write is never inferred to be no effect from its error code alone. Only an ownership conflict with independently unchanged target bytes receives `failed_no_effect_verified`, scoped to that local target.

For an abandoned lock, inspect its operation ID and attempt path, reread the attempt/result, inspect the actual target and ownership manifest, and establish what happened before manually removing the lock. Reconcile through an independent workflow; there is no automatic reconciliation command or assertion that lock age proves safety. Successful historical receipts are audit records and are never consumed as current authorization or reused without fresh input checks. No cross-host lock, power-loss guarantee, remote identity binding, or external authorization mechanism is claimed.

Qualification tests exercise strict negative inputs, zero-write preview, evidence mutation, graph output conflict, same-target locks across different state directories, interrupted/uncertain dispatch, safe receipts, actual local inspection/generation including ownership conflict, and actual graph build/query. Adversarial filesystem writers that remove locks or race symlink changes are outside this single-host cooperative concurrency contract.
