# Interactive local wizard

## Start with what you already have

```bash
python scripts/intune-iac.py start /path/to/working-directory
```

`start` surveys a working directory before anything asks a question. It recognizes:
- wizard, journey and guided sessions, with their step and any conflict;
- workbench stores, with tenant, observed objects, freshness, repository intents and operations;
- Atmos repositories, with Git revision and selectable stack/component pairs;
- supported exports (with their policies) and contexts;
- generated projects, checked against the session that produced them: unchanged, a repository-owned policy edit, or another change;
- modeled services and maintenance operations.

Each item shows four distinct states:
- **discovered:** found on disk.
- **configured:** has what it needs, or the reason it does not.
- **authenticated:** "no live connection"; an export is "source-asserted, not authenticated".
- **qualified:** synthetic evidence says "synthetic only"; nothing is natively or live qualified.

`NEXT` lists concrete commands in a useful order: resume a session, resolve a conflict, collect into an empty store, open the workspace, record a repository with `repository-import` or check it with `repository-status`, start from an unused export, follow an operation with `delivery`. An empty directory gets the two ways to begin. `MISSING` says what is absent, and that offline inspection and preparation remain available without a live connection.

The survey is read-only and offline:
- the walk is bounded and never follows symbolic links (they are listed);
- it skips version-control, environment and evidence directories;
- it opens stores through their normal open, which may roll back an interrupted SQLite journal.

`--json` prints the machine form. Inside the visual workspace, `s` (or `:start [DIRECTORY]`) shows the same survey for the store's parent directory, and an empty store's Estate explains how to get observations.

## The wizard

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
| `restart` | Start again from the first choice. The previous session is kept byte for byte as `SESSION.restart-N.json` beside it, and no output file is touched; `start` lists the kept copy as an earlier session, not one to resume. In repository mode the repository stays chosen. |
| `cancel` | Preserve local files and exit; at conflicts it suspends the session. |
| `new-path` | From a conflict, enter a new staging output directory. |
| `handoff` | At a repository-owned edit (below), end the session in the repository workflow; the result status is `repository_handoff`. |

Selection never edits the original context. In prepared-context mode the session copy retains only the supported bounded context fields; repository mode reconstructs its owned context from the current resolution and capture. Choosing an observed UUID does not prove that its settings or assignments were captured: inspection reports missing or denied relationships as blockers. Names, unknown UUIDs and unsupported context formats are rejected.

Resume with the same session path:

```bash
python scripts/intune-iac.py wizard --session .intune-iac/session.json
```

EOF and Ctrl-C also suspend and save. Sessions store local paths and byte digests; they do not contain copied exports, normalized settings, credentials or execution approvals. Inspection is reconstructed from current files after resume. Changed source or context bytes invalidate the previous inspection and generated review before advancing. File changes, additional files, removed files, symlinks or an edited ownership manifest open the conflict screen. The engine independently checks source-derived output on resume and before finishing; changing a saved session to match a forged manifest cannot create completion evidence.

A review checkpoint requires both source fingerprints and generated-file evidence. Missing prerequisites reject the session instead of claiming a completed generated handoff. A conflict checkpoint must include its reason. The wizard rejects output scopes containing its session, attempt directory, source or context before persisting a change; use a separate staging directory.

Only one wizard may use a session at a time. A second invocation receives `wizard_session_locked` before it can change progress. `save`, `cancel`, EOF and a handled Ctrl-C release this lock. Abrupt process termination can leave the session lock beside the session; no lock expires automatically. For recovery, inspect the lock's session path and process ID, confirm that no wizard still uses that session (a PID alone can be reused), preserve the session and any runner attempt evidence, then manually remove that session lock and resume. An existing runner target lock still requires the separate outcome reconciliation described in `RUNNER.md`.

Repository sessions also save selection hints. On resume and before generation or completion, the wizard re-resolves current repository files and reconstructs the expected context. Repository changes invalidate generated milestones and preserve existing output for review. A saved repository fingerprint alone is never proof: changing that fingerprint cannot keep an old generated milestone. Newly dynamic or unresolved configuration blocks further generation and completion until the local repository can be resolved again.

Conflicts preserve existing output. Choose `review` to see the bounded reason, `new-path` to stage elsewhere, or `cancel` to stop. The wizard never merges or overwrites a conflicting project.

**A repository-owned edit.** One conflict has its own name. Suppose the engineer edited the desired policy in the generated project itself. On reopen, the wizard recognizes it only when all of the following hold:
- `stacks/orgs/reference/dev.yaml` is the only changed file: nothing added or removed, and the ownership manifest is intact;
- the edited file still parses under the repository's literal rules (no duplicate keys, aliases, templates or unsupported scalars), so `workbench repository-import` reads it the same way;
- its values differ from the generated ones only inside `components.terraform.intune-reference.vars.policies.<key>`, which still holds exactly that one key.

The conflict reason is then `repository_owned_edit`:
- `review` shows the exact field changes (strings quoted) and the next steps.
- `handoff` rechecks the files at that moment and ends the session with status `repository_handoff`. The CLI exits 2, as for review-only results.

The generated output keeps its now-stale verification. The wizard never regenerates over it and never calls it verified. The next steps say to copy the edited project into the repository you maintain, commit it, and record it with `workbench repository-import`. `workbench repository-status` then reports whether the repository still matches that intent, and `propose-from-intent` prepares the reviewed change.

Any other change, or one that cannot be established (for example, the source changed too), stays an ordinary `output_changed` conflict. The 17-stage journey (`--journey`) and the guided workflow (`--guided`) recognize the same edit when they fall back to generation. They offer `handoff` the same way and record the lifecycle `repository_handoff`. A handed-off journey cannot be adopted with `workbench adopt`: the first repository intent comes from an explicit `repository-import`. An interrupted or uncertain runner write retains its attempt evidence and target lock; the wizard offers review or a new destination rather than replaying the uncertain operation.

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
