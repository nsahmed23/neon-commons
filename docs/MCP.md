# Local MCP tools

The optional stdio server starts with the same Python environment as the CLI:

```sh
python /absolute/path/intune-iac/scripts/intune-iac.py mcp
```

Configure the host's stdio server command to the absolute path of that virtual environment's Python interpreter, with the script path and `mcp` as separate arguments. Host configuration is deliberately explicit; loading the plugin does not install dependencies, register another server, or acquire credentials.

Tools: `intune_doctor`, `intune_inspect`, `intune_preview`, `intune_run_local`, `intune_graph_query`, `intune_repository_inspect`, `intune_repository_resolve`, `intune_plan_review`, `intune_target_inspect`, and `intune_target_compare`. Repository tools return source-bound structural results without arbitrary configuration values. Plan review takes an `input` file; target inspection takes `input`, and comparison takes `expected` and `observed` files. These reads never authenticate an approver or authorize execution. The server exposes local actions only. Capture, target service collection and CLM calls require explicit CLI invocation and their own configuration. Local-write tools preserve output ownership and emit action receipts. The host remains responsible for granting filesystem access to the intended workspace; this server is a local process, not a multi-user isolation service.

The server uses newline-delimited JSON-RPC, negotiates protocol versions 2024-11-05, 2025-03-26 and 2025-06-18, advertises a fixed tool list, validates arguments, and returns safe tool errors. Requests are sequential. It does not advertise prompts, resources, sampling, subscriptions, cancellation of in-flight writes, HTTP transport, or server-initiated requests. Closing or interrupting the process during a local write may leave an outcome requiring reconciliation; do not remove runner locks without inspecting the output and receipts.

Stdio messages must be UTF-8. Initialization requires a nonempty `protocolVersion`, a `capabilities` object, and `clientInfo` with nonempty `name` and `version`. After the server responds, send `notifications/initialized` before tool requests. Malformed initialization returns a protocol error without opening the session or terminating the process; renegotiation on an existing connection is rejected. Pings remain available during initialization.

Protocol references: [stdio transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports) and [tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools). Local subprocess protocol checks are included. Native host loading remains separate qualification.

## Operator filesystem authority (completion security repair)

MCP starts without file authority. Doctor and protocol negotiation remain usable,
but file tools fail closed until the operator starts the server with absolute
existing `--read-root` and `--write-root` directories. Repeat the flags for
separate capture and output locations. Tool arguments, initialization metadata,
model text, and environment variables cannot grant roots.

Example operator launch:

```sh
python scripts/intune-iac.py mcp --read-root /approved/captures --read-root /approved/repository --write-root /approved/output
```

A write root does not implicitly grant read access. Local actions need a write
root for their journal even when the selected action only reads. Preview checks
the proposed output/journal scopes without creating them. Relative paths,
traversal and symlinked paths are rejected. This is an intentional migration:
old unconfined host configurations must supply reviewed roots.

The host's launch configuration must be outside the evaluated model's write
capability. This is a tool-selection boundary under a cooperative filesystem,
not isolation against a process owner or a concurrent hostile filesystem writer.
Native OS sandboxing and separate identities remain required for that threat.
