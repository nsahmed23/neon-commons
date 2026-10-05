# Baseline reproduction

The original corrected source ran 207 core tests and 417 plugin tests successfully after installing the exact pinned dependencies and allowing local loopback sockets. Earlier missing-dependency and sandbox socket errors remain visible as infrastructure failures. The later integration-interim log records two tests whose mock/launch contracts required updates after deliberate proxy/MCP hardening; these were repaired without relaxing the corresponding redirect or output-conflict assertions. Final new-suite evidence is separate in verification/completion-0.4.
