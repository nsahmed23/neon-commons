# Lease implementation evidence

This directory concerns new `blob_lease.py` functionality. Its initial RED was a missing module, not a defect inherited from the supplied plugin. Subsequent RED cases identify mistakes in this new implementation and are retained alongside the corrected runs. No live tenant, real credential, Azure lease, or provider mutation was used.

The implementation is standard-library Python and introduces no packages. Its live entry point is usable code for the fixed Azure Blob Lease API, but was not invoked against Azure. Its laboratory entry point uses an explicitly laboratory identity binding and cannot mint a live capability. Saved evidence cannot mint either capability.

The local service fixtures are constructed from the primary REST contract. They are not recordings captured from an Azure account. The one-owner fixture tracks the remote owner and expiry independently from the implementation. Lost-response fixtures distinguish a remotely committed action from the locally denied or lost capability. Native transport tests replace the HTTPS connection at the boundary; they do not use production network access.

Evidence interpretation:

- `tests-red.log`: first 13 tests fail because the new module does not exist yet.
- `tests-green-first.log`: those 13 tests pass after initial implementation.
- `terminal-state-red.log`: an attempted renewal after release incorrectly changed its terminal receipt to `lost`; fixed to preserve the existing terminal status.
- `tests-green.log`: current implementation suite result; final combined result is recorded separately.
- `remaining-budget-red.log`: independent renewal/release tests show the token stage receiving five seconds even when only 1.5 or one second of lease authority remains.
- `review-*`: a separate engineer's adversarial test results and findings, including HTTP cancellation behavior.
- `tests-green-combined.log`: 65 passing tests across the 20 implementation tests, 13 independent adversarial tests, and 32 identity tests after the repairs below.
- `sources.json`: dated primary documentation retrieval metadata and implementation API pin. It is a retrieval summary, not an archive of raw source bytes.

Live lease qualification is **BLOCKED**. Needed external evidence includes actual scoped Storage write permission, acquire/renew/release round trips, cross-client conflicts on the same concrete blob, expiry and response-loss behavior, and the deployment's separate mechanism for excluding Graph writers. A blob lease neither provides Graph fencing nor verifies infrastructure recovery.

The protected-host boundary includes Python code and dependencies, the process clock, operating-system trust store, credentials and memory. Opaque classes, exact factory types, and nonserialization protect supported API paths; they do not defend against arbitrary Python execution within this process. A public receipt is only the most recently recorded transition and can be stale.

## Confirmed new-code repairs

| Reproduction | Failure before repair | Repair |
| --- | --- | --- |
| Terminal-state RED | Renewal after release changed `released` to `lost` | Only a currently held capability can transition to lost |
| Independent token budget tests | Renewal/release token stage had a five-second budget with only 1.5/one second left | Credential stage shares the earlier of request deadline and lease expiry |
| Independent stdlib send fixture | After timeout closed the connection, `HTTPConnection.send` opened another connection and dispatched | Disable `auto_open` after the explicit initial connect |
| Independent socketpair response fixture | `Connection: close` detached the response socket; timeout failed to stop a slow body reader | Retain the connected socket for cancellation shutdown and close the response in worker cleanup |

The independent test file also checks the identity transport's corresponding repairs. Identity source belongs to its separate implementation owner; the combined run verifies those shared dependency paths. A `KeyboardInterrupt` cleanup gap in identity transport was separately fixed there. Lease transport already cancelled on an interrupted response wait and now covers thread start and wait with the same cancellation handler.

Verification command (exit 0):

```sh
python -m unittest plugin_tests.test_blob_lease_v5 plugin_tests.test_blob_lease_independent_v5 plugin_tests.test_identity_binding_v5 -v
```

This is bounded functional verification, not a performance benchmark. The slow-response socketpair test uses the real standard-library HTTP parser with in-process connected sockets; it does not contact an external service.
