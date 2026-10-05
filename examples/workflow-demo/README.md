# Local byte-backed resume demonstration

These seeds contain synthetic source, decision, repository HEAD and tool-identity bytes. They demonstrate current-file verification; they are not authenticated repository, binary, tenant or approval acquisition records. Copy a seed before creating metadata. No command invokes OpenTofu, Atmos, Graph, auth, plan, import or apply.

Run from the pack root in the dependency-complete Python environment:

```bash
cp -R examples/workflow-demo/early /tmp/intune-session-early
python tools/session-reference.py create --offline --root /tmp/intune-session-early --saved-state object_selection --artifact repository_context:repository.json --artifact source:source.json --artifact decisions:decisions.json
python tools/session-reference.py inspect --offline --root /tmp/intune-session-early
python tools/session-reference.py resume --offline --root /tmp/intune-session-early --resume
```

The verified prefix is repository/source/inventory/selection; the saved frontier caps it before selection, so resume stays `object_selection`.

```bash
cp -R examples/workflow-demo/partial /tmp/intune-session-partial
python tools/session-reference.py create --offline --root /tmp/intune-session-partial --saved-state partial_generate --artifact repository_context:repository.json --artifact source:source.json --artifact decisions:decisions.json --artifact normalized:normalized.json --artifact provider_evidence:provider.json
python tools/session-reference.py inspect --offline --root /tmp/intune-session-partial
python tools/session-reference.py resume --offline --root /tmp/intune-session-partial --resume
```

The partial example independently verifies the repository/source/inventory/selection/ownership/mapping prefix. The preservation oracle recomputes unsupported-definition blocking. Resume returns `partial_generate`. Editing the saved stack fingerprint cannot turn it into `generate`.

Delete or edit `source.json` and run resume again: dependent receipts are invalid. Delete a required input or change `.git/HEAD`: repository becomes the earliest prerequisite. A modified receipt-index file with an unchanged saved index hash returns recovery. `cancel --offline --root PATH` retains progress; `resume` without `--resume` stays cancelled, while explicit `--resume` revalidates bytes and never reuses authorization. Existing session metadata makes create fail instead of overwriting it.
