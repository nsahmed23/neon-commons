# Full local journey qualification

The actual `wizard --journey` CLI reached all 17 receipt-derived stages with the bundled synthetic capture. It ran from a directory outside the repository, generated the real engine proposal, executed a bounded synthetic child process against a saved plan, independently reconstructed its operation journal and state, and reached `complete_simulation`. All six qualification checks passed, including unchanged implementation hashes during the run.

The compact retained evidence is `journey-final-evidence/`. `qualification.json` binds source and implementation hashes; `transcript.json` records exact commands/answers; `cli.stdout.txt` and `cli.stderr.txt` retain the interaction; the stage receipts, generated proposal, saved plan and operation events are included. `SNAPSHOT.json` explicitly identifies the omitted runtime executable and its hash. This is a record-only snapshot, not a portable runtime or signed attestation. The full current operational session was independently reconstructed after the CLI completed and still returned 17 verified stages, `complete_simulation`, and `live_ready: false`.

`journey-red.txt` records the test-first missing-implementation failures. `journey-green.txt` retains the 19-case journey regression pass before the final protected-process resource hardening. The actual CLI qualification and post-CLI reconstruction were rerun successfully against the final hardened source; the release integration suite supplies the final complete source regression. Tests exercise UUID/target binding, source-byte invalidation, rehashed generated manifests, forged assurance and session claims, action vocabulary/contract parity, back/edit/cancel, interrupted approvals, known predispatch rejection, uncertain generation, and suspended execution receipt recovery without replay. A separate production-shaped case verifies that inactive `.tf.txt` candidates remain inactive and the provider qualification gate remains present.

The simulation is deliberately a policy-hash model. Its desired state is derived from every selected normalized object plus source and target hashes. It does not execute the Microsoft365 provider, Graph requests, native Atmos, import remote state, authenticate a tenant, or establish remote convergence. Production-shaped input is still the source of its proposal; no hidden synthetic capture replaces it. Unsupported mapping cannot enter the executable simulation. Live-review mode stops at planning with genuine identity, backend, writer, provider, approval and executor gates unqualified.

The release's broader evidence is mapped in `capability-coverage.csv`: 37 rows connect E01–E10 and individual workload families to immutable source/skill pins, implementation, scenarios, independent assertions, evidence, and remaining gaps. Actual native Atmos/OpenTofu experiments and actual provider source/native validation have their own evidence paths and denominators. Neither those labs nor a high test count establishes enterprise readiness. Cohort intent in the older guided route remains intent; all non-implemented policy/app/script/enrollment/platform families are explicitly staged, reference-only or unsupported.

Reproduce using the pinned runtime dependencies:

```bash
python -m unittest plugin_tests.test_journey_completion
python scripts/qualify-journey.py --cli --output /absolute/fresh/operational --snapshot /absolute/fresh/evidence
```

Reconstruction intentionally invalidates bound native plans when protected runtime source bytes change. Intermediate runs during simultaneous security hardening therefore required fresh qualification. The retained final CLI receipt was produced after the protected implementation's final freeze and checks that no such change occurred during the run. No live credentials, tenant mutations, publication or commits were involved in this lane.

The prior compact snapshot is preserved under `journey-history/pre-resource-caps-evidence/`. Its current-source invalidation is recorded explicitly: 11 earlier stages verify, then the protected implementation binding stops reconstruction at `plan`. It is historical evidence, not current-source qualification. The refreshed snapshot retains `PACKAGING.json` with the exact `.tfstate` to `synthetic-state-evidence.json` byte-preserving path mapping; the operational source retains its original state file.
