# Independent capture proxy boundary review

PASS_SCOPED. The failed final01 strict test patched `capture.build_opener`, which no longer exists after capture adopted the existing bounded native transport. The product route remains unchanged from commit `e8c581dcfbb4543609eebb2d48eacbadec026ee8`: `_http_transport` builds an explicit Graph request; `_NativeTransport` uses the real stdlib `HTTPSConnection` on port 443 and the system TLS trust store. No ambient proxy lookup or redirect mechanism participates.

The repaired test keeps the original security requirement. It observes `socket.create_connection` destination beneath the actual native worker and actual HTTPSConnection, then blocks before DNS/network/TLS/credential dispatch. Both clean and hostile HTTP/HTTPS/ALL_PROXY and SSL_CERT environments select Graph:443; the same observer sees the hostile proxy when exercised through a proxy-sensitive urllib control. The test checks externally observable route/failure behavior instead of assuming an internal opener constructor.

`probe.py` and `run-01/receipt.json` are the separate independent probe. Six checks passed and reviewed product bytes remained unchanged. `REVIEW.json` binds the exact repaired test bytes, unchanged transport modules and original failed strict log. Existing failed evidence is preserved. No source or test edits were made by this reviewer.

This focused evidence does not demonstrate successful TLS, live Graph, tenant/device qualification or organizational approval. Existing native socket/TLS fixtures and the next complete strict run remain separately scoped.
