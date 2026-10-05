"""Counterexamples from the independent v0.2 host audit."""
import io
import json
import unittest

from intune_iac.mcp import serve


def initialize(params=None):
    return {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": params if params is not None else {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "audit", "version": "1"}}}


class MCPAuditTests(unittest.TestCase):
    def exchange(self, messages):
        incoming = b"".join(json.dumps(message).encode() + b"\n" for message in messages)
        output = io.StringIO()
        code = serve(io.BytesIO(incoming), output)
        self.assertEqual(code, 0)
        return [json.loads(line) for line in output.getvalue().splitlines()]

    def test_malformed_initialize_is_rejected_without_losing_next_request(self):
        base = initialize()["params"]
        for field, value in (("protocolVersion", []), ("protocolVersion", {}),
                             ("protocolVersion", None), ("capabilities", []),
                             ("clientInfo", {}), ("clientInfo", {"name": [], "version": "1"})):
            with self.subTest(field=field, value=value):
                bad = dict(base, **{field: value})
                responses = self.exchange([initialize(bad), {"jsonrpc": "2.0", "id": 2, "method": "ping"}])
                self.assertIn("error", responses[0])
                self.assertEqual(responses[0]["error"]["code"], -32602)
                self.assertEqual(responses[1]["result"], {})

    def test_missing_required_initialize_metadata_is_rejected(self):
        for omitted in ("protocolVersion", "capabilities", "clientInfo"):
            with self.subTest(omitted=omitted):
                params = initialize()["params"]
                del params[omitted]
                responses = self.exchange([initialize(params), {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])
                self.assertIn("error", responses[0])
                self.assertEqual(responses[0]["error"]["code"], -32602)
                self.assertIn("error", responses[1])

    def test_operations_wait_for_initialized_notification_and_cannot_reinitialize(self):
        responses = self.exchange([initialize(), {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, initialize()])
        self.assertIn("error", responses[1])
        self.assertIn("tools", responses[2]["result"])
        self.assertIn("error", responses[3])

    def test_stdio_rejects_utf16_before_initialization(self):
        raw = (json.dumps(initialize()) + "\n").encode("utf-16-be")
        output = io.StringIO()
        serve(io.BytesIO(raw), output)
        reply = json.loads(output.getvalue())
        self.assertIn("error", reply)
        self.assertEqual(reply["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()
