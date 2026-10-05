# Provenance and redistribution notes

Original Appendix B reference algorithms, schemas, tests and synthetic fixtures were authored for this handoff. The runtime does not bundle upstream provider/SDK executables, terminal libraries, proprietary binaries or agent-harness implementations. The 0.3.0 source archive now includes selected raw upstream code and licenses for reproducible source qualification, as itemized below. Those files retain their upstream terms; inclusion is not a relicensing grant.

Deployment Theory's pinned LICENSE identifies Mozilla Public License2.0, copyright2025 Deployment Theory. The selected Microsoft Azure skill frontmatter identifies MIT. Other source license fields remain null when not verified; their implementations are reference-only until full file-level terms/notices are acquired. Do not infer the engine's license applies to skills or copied code. Review dependencies and notices before future vendoring/distribution; do not change their license to match a new project.

The four original documents and user-supplied audit/prompt are retained as handoff inputs. Their quotations/citations and unverified historical claims remain attributed, not newly endorsed. `citation-repair-ledger.csv` preserves unresolved references rather than fabricating URLs. Docs retrieved from Microsoft/OpenAI/Anthropic/Cloud Posse were used for contract research; no full manuals are mirrored.

Release 0.2.2 includes derived corpus metadata from Stéphane Robert's
`terraform-dsoxlab-training`, commit `86b69d2292485d179698f5b9bf648a29f935e216`,
under Creative Commons Attribution 4.0 International. Attribution, the exact
upstream license, extraction changes and file hashes are retained in
`research/terraform-catalog/` in the source distribution. Encrypted reference
solutions are not bundled or decrypted. The locking replay obtains and hash-checks
the original plaintext tests from a separately acquired checkout, preserves those
test bytes, and explicitly documents its authored solution and version adaptation.

Atmos and Cloud Posse test-helpers (Apache-2.0) and tfmigrate (MIT) were inspected
for workflow ideas. Their selected pins, source hashes and reuse decisions are in
`research/atmos-resources/`. Their implementations and executables are not vendored.
The native adoption fixture and qualification runner are original code.

For 0.3.0, `research/provider-qualification/raw/` contains selected byte-preserved
Deployment Theory microsoft365 provider source (MPL-2.0), Microsoft Graph beta
SDK source (MIT), and Microsoft Kiota abstraction, JSON writer and HTTP adapter
source (MIT). Each source root includes its acquired LICENSE. The source ledger
records pinned identities and file hashes. `labs/provider-contract/patched/`
contains a modified MPL-2.0 provider GET helper, its LICENSE and explicit
NOTICE.md; the unified patch and original/modified hashes identify the changes.
This is source for a candidate patch and lab, not a redistributed qualified
provider binary. Generated test staging copies retain these original terms.

`research/enterprise-target/raw/` includes selected OpenTofu Azure backend source
with its acquired MPL-2.0 LICENSE and selected Cloud Posse Atmos source with its
Apache-2.0 LICENSE. Original file notices are retained. The project uses them as
research evidence; they are not imported into the Python runtime.

The CycloneDX 1.6 JSON schema is retained unmodified for validating the dependency
artifact inventory, under Apache-2.0, alongside `CycloneDX-LICENSE` in
`research/enterprise-dependencies/`. Its source identity and hashes are recorded
with the schema-validation receipt. Runtime dependency wheels and their installed
code are not bundled; exact package metadata and artifact hashes are recorded in
`dependency-lock.json` and the source distribution's dependency inventory.

The nine newly supplied inspiration repositories were acquired and selected files
inspected. Their runtime code, skills, hooks and installers are not copied into
this plugin. `research/enterprise-inspiration/` records metadata and reuse
decisions. A missing license is not treated as permission to copy implementation.

No claim of legal compatibility or enterprise approval is made. The organization chooses a release license and approves third-party material before distributing an implemented plugin.

## Completion checkpoint acquisition

The source distribution includes separately licensed review/evaluation inputs under research/completion/security/acquired and provider/lab evidence under their existing source paths. Source commits, acquisition digests, original license files and reuse limitations are retained in their manifests. Cloudflare audit material is MIT; Visa harness material is Apache-2.0. No Visa implementation, external skill installer, Vercel/Cloudflare service dependency, or catalog script was added to the runtime. The separate source-catalog evidence archive is review material; consult each original license and nested notice before reuse. Unknown or absent licenses remain deferred.
