# Interactive local wizard

Run from the installed plugin or the build checkout with its documented Python dependencies:

```bash
python scripts/intune-iac.py wizard \
  --session .intune-iac/session.json \
  --repo /path/to/atmos-repository \
  --input /path/to/local-capture.json
```

Repository mode discovers physical stack manifests and their selectable, literally resolved Terraform components. Choose a displayed stack, component, and observed policy UUID by exact value or displayed number. `--stack deploy/dev --component policy` supplies the first two selections. If `--input` is omitted, the wizard asks for the local capture after the repository selection. The wizard never captures tenant data or authenticates to a cloud service.

The policy choice creates an owned context JSON file beside the session. It records the selected stack, component, implementation, current repository source fingerprint, and `authorization: emit_only`. The tenant UUID comes from the local capture and is explicitly **source-asserted**; repository labels do not authenticate it. No prepared context file is needed. `--repo` and `--context` cannot be combined. Repository values and credentials are not copied into the session or generated context.

The output prompt defaults to `intune-proposal` beside the session. Press Enter to accept, supply another staging directory, or pass `--output`. The selected output must have an existing parent. The repository is read-only; output is staged separately.

Repository resolution does not qualify the existing bounded synthetic generator for a new target. Synthetic captures in repository mode show `syntheticcore_target_unqualified` and cannot generate IaC; use `review` for the inspection handoff. Production captures can generate review artifacts and cannot generate active `.tf` files or executable command cards. The exact plugin exporter contract may also produce inactive `candidates/components/terraform/<component>/main.tf.txt` when its bounded policy mapping is complete. Candidate text does not prove repository ownership, tenant authenticity, or provider qualification. The wizard never runs Atmos, Terraform, OpenTofu, provider plugins, imports, or applies.

The original prepared-context flow remains available without `--repo`:

```bash
python scripts/intune-iac.py wizard \
  --session .intune-iac/session.json \
  --input examples/supported/input/export.json \
  --context examples/context.json \
  --output /tmp/intune-proposal
```

Use a new output directory whose parent already exists. Omit input, context or output flags to enter those paths interactively. The context selects a policy by UUID and tenant UUID; duplicate display names never determine selection.

The wizard performs a real local inspection through the fixed action runner. It prints the selected policy UUID, mapping, coverage count and blocker codes. For the supported synthetic fixture, type:

```text
generate
finish
```

`generate` previews and dispatches the qualified local generator, verifies the written proposal, and opens its review screen. `finish` completes the local handoff. Completion is a local workflow result: it does not assert tenant validation, provider qualification, approval, import, apply or cloud execution. The current bounded active mapping is synthetic. Production captures and synthetic captures with unresolved relationships produce review-only proposals; blockers remain visible and cannot be answered away.

At the preview, `review` completes an inspection handoff without generating files. Unavailable or invalid inspection must first be repaired using a complete local source and context.

| Command | Behavior |
| --- | --- |
| `generate` | Generate the inspected local proposal from the preview screen. |
| `review` | Finish an inspection handoff, or describe the conflict at a conflict screen. |
| `finish` | Complete the verified generated proposal review. |
| `back` | Return to the previous decision screen. |
| `edit source` | Enter another local export path, then context and output. |
| `edit context` | Enter another bounded context path, then output. |
| `edit stack` / `edit component` | Reopen repository target selection in repository mode; `edit context` also reopens component selection in that mode. |
| `edit policy` | Reopen the observed UUID choices in repository mode. |
| `edit output` | Enter another staging output directory. |
| `select UUID` | Validate the UUID against the observed local policy inventory, create a session-owned context copy, then reinspect it. |
| `save` | Save the current decision screen and exit suspended. |
| `cancel` | Preserve local files and exit; at conflicts it suspends the session. |
| `new-path` | From a conflict, enter a new staging output directory. |

Selection never edits the original context. In prepared-context mode the session copy retains only the supported bounded context fields; repository mode reconstructs its owned context from the current resolution and capture. Choosing an observed UUID does not prove that its settings or assignments were captured: inspection reports missing or denied relationships as blockers. Names, unknown UUIDs and unsupported context formats are rejected.

Resume with the same session path:

```bash
python scripts/intune-iac.py wizard --session .intune-iac/session.json
```

EOF and Ctrl-C also suspend and save. Sessions store local paths and byte digests; they do not contain copied exports, normalized settings, credentials or execution approvals. Inspection is reconstructed from current files after resume. Changed source or context bytes invalidate the previous inspection and generated review before advancing. File changes, additional files, removed files, symlinks or an edited ownership manifest open the conflict screen. The engine independently checks source-derived output on resume and before finishing; changing a saved session to match a forged manifest cannot create completion evidence.

A review checkpoint requires both source fingerprints and generated-file evidence. Missing prerequisites reject the session instead of claiming a completed generated handoff. A conflict checkpoint must include its reason. The wizard rejects output scopes containing its session, attempt directory, source or context before persisting a change; use a separate staging directory.

Only one wizard may use a session at a time. A second invocation receives `wizard_session_locked` before it can change progress. `save`, `cancel`, EOF and a handled Ctrl-C release this lock. Abrupt process termination can leave the session lock beside the session; no lock expires automatically. For recovery, inspect the lock's session path and process ID, confirm that no wizard still uses that session (a PID alone can be reused), preserve the session and any runner attempt evidence, then manually remove that session lock and resume. An existing runner target lock still requires the separate outcome reconciliation described in `RUNNER.md`.

Repository sessions also save selection hints. On resume and before generation or completion, the wizard re-resolves current repository files and reconstructs the expected context. Repository changes invalidate generated milestones and preserve existing output for review. A saved repository fingerprint alone is never proof: changing that fingerprint cannot keep an old generated milestone. Newly dynamic or unresolved configuration blocks further generation and completion until the local repository can be resolved again.

Conflicts preserve existing output. Choose `review` to see the bounded reason, `new-path` to stage elsewhere, or `cancel` to stop. The wizard never merges or overwrites a conflicting project. An interrupted or uncertain runner write retains its attempt evidence and target lock; the wizard offers review or a new destination rather than replaying the uncertain operation.

Generated review starts with `README.md` and `generated-files.json`. Synthetic proposals also include `adoption/coverage.json`, `adoption/field-accounting.json` and `adoption/capability.json`; blocked synthetic proposals have `BLOCKED.json`. Production capture reviews include `review/normalized.json` and `BLOCKED.json`, and emit no active `.tf` files or executable command cards. The source export remains the restricted original input.

For automation, use the separate noninteractive `inspect`, `generate` and `action preview` commands documented in the main README. The wizard's Python API accepts injectable terminal callbacks:

```python
from intune_iac.wizard import run_wizard

result = run_wizard(
    "session.json", repo="/path/to/repository", input_path="export.json",
    stack="deploy/dev", component="policy",
    output_path="new-project", input_fn=input, output_fn=print,
)
```

The returned status is `complete`, `review_only`, `suspended`, `cancelled` or `blocked`. `execution_authorized` is always false for a valid workflow result. None of the commands accepts cloud credentials or authorizes native/cloud actions.
