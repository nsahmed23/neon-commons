# Protected service evidence in the Workbench

`workbench service-link` links a registered service operation to one immutable
tenant/object identity. It persists navigation and the exact manifest digest;
it neither approves nor dispatches an operation. The complete text terminal has
the equivalent `service-link JOB_ROOT POLICY_PATH` command after `select ID`.

```bash
python scripts/intune-iac.py workbench service-link --help
python scripts/intune-iac.py workbench service-link --root STORE --object UUID --job-root JOB --policy POLICY
python scripts/intune-iac.py workbench views --root STORE --object UUID
```

Each view reopens the service registry and immutable manifest. The proposed view
shows exact saved-plan bytes, signature domain, repository/run context, provider
and backend binding, and the durable operation journal. A changed or unavailable
link is explicitly unknown. Viewing, reopening or linking cannot run a worker.

A successful deployment baseline additionally requires known completed host
execution, the exact independent reconciliation event and its published Graph
capture. An independently converged state after an uncertain execution remains
visible as convergence with unresolved execution provenance. It does not become
a successful deployment baseline. Service readback does not establish a
no-change second plan or device effectiveness.

Literal observations remain inspectable when service collection is complete but
management mapping is unsupported. `observed.raw_capture_observation` retains
the collection timestamps, raw policy/settings/assignments and mapping blockers.
The last-good normalized snapshot stays separate. A deployment with only raw
unsupported evidence exposes that evidence and reports normalized comparisons
unknown; it never invents a mapped snapshot or relaxes the adapter.

The source scope comes from the signed worker manifest. Comparisons associate
tenant/object identity, not a guessed match between a local repository path and
a remote Git URL. Actor attribution remains unknown unless separate evidence
establishes it. A laboratory transport keeps its laboratory evidence class.

Local SQLite, journal and path links are cooperative evidence, not a protected
organizational audit anchor. Native platform qualification, protected retention,
AppSec disposition and organizational production approval remain separate gates.

Development evidence is `evidence/epoch-20261007-r4/service-views/`: actual CLI,
store, laboratory reader and TLS readback tests; explicit host-journal fixtures
are not execution evidence. The independently signed Docker/TLS journey and the
native provider journey have their own receipts and scopes.
