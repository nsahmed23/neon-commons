# Exact local source intent in the protected worker

`worker-service-operation/2` adds an exact source-authoring binding to the existing protected service. It uses the existing `signed-worker-service-approval/1` signature/domain, approval policy, authority database, host and dispatcher. Version 1 remains unchanged and cannot claim the source bridge by supplying an optional capability.

This is a bounded local source-integrity profile. It does not authenticate GitHub origin, identify a commit actor, activate CI, grant management coverage or authorize production. The logical GitHub repository association is explicit review material in the signed operation; a local remote name does not establish it. Unsupported policy mapping remains unsupported.

The trusted controller first calls:

```python
source_intent = worker_source_intent.bind_source_intent(
    store=store, intent_id=intent_artifact_id, adapter=provider_adapter,
    logical_repository=reviewed_repository_url,
    git_executable=absolute_git_path, git_sha256=reviewed_git_sha256,
)
manifest = worker_service.make_intent_manifest(
    source_intent=source_intent, **the_existing_exact_operation_arguments,
)
runtime = worker_service.laboratory_runtime(
    native_protocol=True, source_intent=source_intent,
    **the_existing_typed_runtime_arguments,
)
```

The live runtime accepts the same capability argument only alongside its existing real identity, credential, transport, storage and approval prerequisites. These calls prepare process-held capabilities; they do not dispatch a worker. A JSON binding cannot replace the capability.

The factory uses the existing pinned Git reader and literal Atmos resolver. It binds the latest selected workbench intent, immutable tenant/object/resource address/backend, local root identity, exact commit/tree/blob evidence, full selected source bytes, effective inputs, provider locks and materialized native configuration. The currently reviewed authoring profile is one `intune-policy` component in stack `worker`, using the literal `/vars/native_policy` value through the fixed JSON component. The authoritative component and generated worker configuration are distinct, both checked.

Git verification initially runs on the main thread. Every subsequent controller/watchdog/broker guard rechecks the exact root, intent, selected source, configuration, locks, pinned Git executable and bounded Git object-store/configuration bytes without spawning from a worker thread. Denied subtrees fail closed. The census admits at most 1,024 object-store files, 1,024 directories and 32 MiB; the service document limit can impose a narrower bound. Repacking, replacing, adding or removing bound Git storage invalidates the capability even if a new commit would have equivalent content. Unbounded or unsupported stores require a separately qualified profile; they are not silently omitted.

The version 2 validator also cross-checks the declared logical repository, stack, component, physical backend URI, tenant, object, source revision, effective inputs, generated source and lock digests against the actual operation/run/provider bindings. The held capability is rechecked before approval consumption and at every active guard. A changed source does not cause a replacement plan to be generated. Hostile-host atomicity and read-to-write races remain separate qualification concerns.

The actual text preparation/inspection commands remain:

```text
python scripts/intune-iac.py service prepare --manifest MANIFEST --job-root NEW_JOB --policy POLICY
python scripts/intune-iac.py service review --job-root JOB --policy POLICY
python scripts/intune-iac.py service status --job-root JOB --policy POLICY
python scripts/intune-iac.py service attach --job-root JOB --policy POLICY
```

The complete manifest, including source binding, is available through the existing service review and linked workbench proposed view. There is no CLI flag that deserializes an execution runtime.

Local evidence is indexed by `work/evidence/epoch-20261007-r4/worker-provider/adoption-staging/source-intent-service/PROPOSAL-02.json` in the complete recovery corpus. It retains the main-thread-only guard failure, the denied-census failure and their repairs. The final capability passed 24 focused Git/materialization/signature/zero-dispatch rejection checks; 36 ordinary service regression tests remain a separate reused scope. Independent review has 18 assertions, eight overlapping the earlier capability review; counts must not be summed. Those broader qualifiers rely on the complete retained laboratory corpus and exact disposable paths; their exact invocations and inputs remain with each receipt.

The source package also contains a selfcontained six-method changed-code gate:

```text
python -B -m unittest -v plugin_tests.test_worker_source_intent_r4
```

It creates its own disposable Git/Atmos repository and workbench store, tests actual import/materialization and a real thread recheck, rejects closed-manifest/JSON/serialization substitutions, and verifies actual prepared jobs reject changed source and locks before consumption or dispatch. It requires the documented pinned signing-validator prerequisite, `/usr/bin/git` (or an explicit `INTUNE_TEST_GIT_EXECUTABLE`) and `/usr/bin/openssl`; it does not use retained tenant/laboratory captures, Docker or network access. Its denied-directory error is an injected filesystem failure; the separate retained census experiment exercised a real unreadable subtree. Signature execution and native worker success are outside this narrow test scope. These cases overlap the broader evidence and must not be added as independent end-to-end journeys.

Successful native version 2 execution, connected source review and external platform qualification are still required after this insertion. Existing version 1 adoption/maintenance evidence remains valid only at its recorded scope; it does not retroactively establish this bridge.
