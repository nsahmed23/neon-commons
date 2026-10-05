# Offline workflow task review

Review date: 2026-09-30. Scope: `reference/workflow.py`, `tools/session-reference.py`, `reference/approval.py`, v2 session/receipt schemas, wizard/resume documentation and their focused tests. This review evaluates local offline consistency and routing. It does not treat local receipts as signed evidence or external execution authority.

## Specification compliance verdict: PASS

The final implementation creates actual receipt/index/session files, rereads retained bytes, validates their registered schemas and hashes, closes prerequisite artifact dependencies and requires a verified prerequisite receipt prefix. Resume intersects saved completion with current verification and caps it before the saved frontier. Explicit local resume is required after suspension/cancellation; every observed result retained `external_execution:false` and `authorization_reused:false`.

Independent full-path verification used actual generated project files, a raw-source byte receipt, parsed provider lock, pinned synthetic tool byte identities, complete effective-input manifest, structured identity binding, validation report, cohort and plan bytes. All nine milestones completed; an unchanged session saved at `qualification_handoff` returned that state with no receipt errors. The same fully verified evidence saved at `object_selection` remained at that early frontier.

| Actual retained-byte control | Observed result |
|---|---|
| Changed cohort, early `object_selection` session | `object_selection`, with `invalidated:cohort_digest` |
| Changed cohort, late session | `adoption_preview` |
| Changed stack fingerprint, independently verified partial mapping | `partial_generate` |
| Edited generated component file | `generate` |
| Added unmanifested component `extra.tf` outside the declared repository path | `generate` |
| Changed pinned engine bytes | `provider_mapping` |
| Changed repository HEAD | `repository_inspection` |
| Missing inventory or validation receipt | Earliest missing prerequisite, without late advancement |
| Missing prerequisite dependency, wrong dependency hash or cyclic dependency | Dependent source completion rejected |
| Corrupt/unknown session, duplicate JSON key, unsafe path or symlink root | Controlled offline recovery |
| Symlink substituted for source artifact | Source completion rejected |
| Modified index with unchanged saved index hash | `receipt_index_hash_changed` recovery |
| Contradictory structured repository revision/dirty-input binding | Generation rejected; resume returns `generate` |

The structured approval comparator checks complete schema-valid bindings and aware validity timestamps, including object/null authentication branch changes. The legacy comparator retains its explicitly limited historical behavior. Neither comparison authenticates an approver.

## Code quality verdict: PASS within the documented offline boundary

Four concrete defects found during this review were reported and repaired before this verdict:

1. Duplicate artifact kinds could enter the valid-ID set before rejection, allowing malformed evidence to retain completion. Global duplicate-kind preflight and publication after every check now reject this case.
2. Malformed real HCL lock bytes raised an uncaught Lark parser exception. The parser boundary now converts that failure into controlled milestone rejection.
3. Concurrent cooperating creators could both succeed and overwrite session metadata. Exclusive, no-follow creation locking now permits one creator and rejects the other.
4. Structured `git_revision` and `relevant_dirty_files_digest` could contradict reconstructed repository facts while all nine milestones completed. Generation now binds both fields to reread facts. An independent repeat of the original reproducer now completes only the first six milestones and returns `generate`.

The final focused run passed **46/46 tests**, including actual generated/validated/reviewed late-session controls, concurrency, malformed-lock, duplicate-kind, repository-binding and lifecycle hash controls:

```bash
PYTHONPATH=/workspace/scratch/26b6d364cfda/correction-validation-deps \
PYTHONDONTWRITEBYTECODE=1 python -m unittest \
  evaluations.test_repaired_workflow evaluations.test_approval \
  evaluations.test_wizard evaluations.test_repaired_contracts -v
```

No provider, cloud, authentication, plan, import, apply or native execution was performed. Documented exclusions—external authenticity, authenticated acquisition, adversarial parent-directory races and transactional multi-file crash recovery—remain qualification boundaries rather than missing offline features. No remaining blocking defect was identified in this scope.
