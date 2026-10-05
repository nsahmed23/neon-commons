# Independent Blob lease review

Final result: 13 independent adversarial test methods pass after the source owners repaired the reachable defects below. No external service calls were made. Live Azure qualification remains BLOCKED; this is not Graph fencing or production acceptance.

| Finding | Before repair | Verified correction |
|---|---|---|
| LEASE-REVIEW-01 | Token request timeout was 5 seconds when conservative lease lifetime was only 1.5 or 1 second. | The token exchange budget is capped by the minimum request deadline and previous lease expiry. |
| LEASE-REVIEW-02 | KeyboardInterrupt during the result wait bypassed stop(); a delayed connect could resume and begin the credential request after caller cancellation. | Cancellation cleanup now covers BaseException around worker start/result wait; delayed connect checks cancellation before dispatch. |
| LEASE-REVIEW-03 | Timeout closed the connected socket after the cancellation check but before request send. stdlib auto_open reconnected and sent after the caller returned. | Automatic reconnect is disabled immediately after the explicit connection; a closed socket cannot trigger fresh dispatch. |
| LEASE-REVIEW-04 | Connection: close detached conn.sock while HTTPResponse retained the socket. A slow body kept the worker and one of four slots alive after the caller deadline. | The native transports retain the connected socket separately for cancellation shutdown and close the response in the worker finally path. |

The combined independent RED log contains four failing assertions/subtests: renewal and release token budgets, lease reconnect after timeout, and lease detached-response cleanup. Identity transport issues were independently reproduced earlier and repaired by their owner before this combined RED run. The final independent GREEN run covers both native transports.

Run from the project root:

```sh
python3 -B -m unittest plugin_tests.test_blob_lease_independent_v5 -v
```

The owner-state fixtures cover response loss after the modeled remote operation has committed, expiry followed by a new owner, same-role concurrency, exact credential-handle identity, opaque storage tokens, fixed origins, and the explicit absence of Graph authority. Native transport fixtures exercise cancellation and stdlib socket ownership. All workers/producers are joined during fixture cleanup; socketpairs stay inside the local process environment.

## Evidence

- `review-independent-red.txt`: genuine failing run, with `review-red-source-hashes.json`.
- `review-independent-green.txt`: final 13-test passing run, with `review-green-source-hashes.json`.
- `review-independent.json`: machine-readable findings, scope and limitations.

## Limits

- No live Azure lease, RBAC, tenant, TLS endpoint, Graph or Intune calls were made.
- Default optional expected_etag means ownership only; state revision pinning needs an explicit fresh condition and separate re-observation.
- An OS resolver can outlive a deadline; worker creation remains capped at four and cancellation prevents subsequent credential dispatch.
- The local socketpair fixture exercises stdlib response ownership and cleanup, not live TLS interoperability.
- The protected Python host and credential-holding process remain trusted; malicious mutation of private capability internals is not an isolation boundary.

Only the independent test file and review-* artifacts were edited by this reviewer. Source fixes belong to the lease and identity owners. Sealed Wally evidence was not modified.

The detached-response regression explicitly asserts that a local socketpair was created, stdlib detached the response socket, and body reading started. A host denying socketpair produces an explicit skip, never a cleanup success. The final recorded run exercised both transports and had zero skips.
