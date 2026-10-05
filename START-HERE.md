# Intune/Atmos 0.5.0 engineering candidate

Start with [acceptance and remaining production gates](docs/PRODUCTION-COMPLETION-ACCEPTANCE.md)
and [current verification](RELEASE-VERIFICATION.md). This is the final source
package for this engineering run; enterprise production acceptance is BLOCKED.

- [Provider wizard and recovery](docs/PROVIDER-JOURNEY.md)
- [Explicit authenticated identity contract](docs/IDENTITY-BINDING.md)
- [Signed approval and private outcome records](docs/SIGNED-APPROVAL.md)
- [Azure Blob lease mechanics and limits](docs/BLOB-LEASE.md)
- [Native labs](docs/LABS.md) and [synthetic estates](docs/SYNTHETIC-LABS.md)
- Current findings, evidence and capability supplement: `research/production-completion/`
- Earlier catalog, threat, family and requirement inventories: `research/completion/`

Run the source verification using the pinned Python environment:

```sh
python scripts/verify-plugin.py --include-core --output /absolute/new-verification
```

This command returns nonzero for failed or incomplete coverage. Do not remove a
skip or weaken an assertion to make it green. Provider native tests additionally
require the pinned tools and host capabilities documented by the lab contracts.

The supplied Wally 3.0.0 source and repaired Wally 3.0.1 are a separate project.
Wally remains a read-only application performance reviewer; its results cannot
authorize this wizard or certify security. See the separate Wally source and
sealed evaluation evidence. Earlier handoff prompts/reports are preserved as
historical inputs, not current completion claims.
