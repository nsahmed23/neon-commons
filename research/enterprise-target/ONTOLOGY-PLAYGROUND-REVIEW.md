# Ontology Playground: useful constraints, unsuitable defaults

Inspected checkout: `microsoft/Ontology-Playground`, commit
`42a5e5ec170c1e76343886b9d5ba7a55959cb112`, MIT license, Microsoft copyright.
The root cloned the repository. This workstream read selected code only; no npm
install, build, browser session, cloud service or upstream test suite was run.
No source from this repository was copied into the Intune runtime.

The useful transfer is an executable **relationship contract**, not a larger
picture of the same nodes. `src/data/ontology.ts` distinguishes entity types,
instances, identifier properties, relationship endpoints, cardinality and
relationship attributes. `src/store/designerStore.ts` keeps draft changes
separate from the displayed ontology and validates duplicate entity/relationship
IDs, endpoint existence and identifier-property types before export. These are
concrete patterns for preserving identity and separating suggestions from facts.

For our graph, the highest-value next change is a centralized predicate registry
covering every edge with source/target types, allowed epistemic status, and
conditional cardinality. Existing `graph.py` already checks many node-specific
relationships, exact targets and derived Atmos facts, but its `edge_types` table
only covers selected derived predicates. A complete registry should enforce:

| Relationship | Required check | Counterexample to reject |
|---|---|---|
| Policy → Tenant | One tenant matching policy cloud/tenant identity | An edge to a similarly named tenant or another cloud |
| SettingValue → Policy / SettingDefinition | Exactly one owning policy and definition; opaque setting ID retained | Renumbered setting or two definition targets |
| Assignment → Policy / Group / Filter | One policy; exactly one inclusion **or** exclusion target; filter edge agrees with mode; unavailable capture remains unknown | Inclusion and exclusion edges together, orphan filter, fabricated empty desired target set |
| ComponentInstance → EffectiveConfiguration | Exactly one effective configuration only when resolved; source/selection digests verify | Resolved node with no configuration or multiple conflicting configurations |
| EffectiveDependency → ComponentInstance | Exactly one resolved target only when scope/context is independently supported | Missing target silently removed, or same display name in a different stack treated as identical |
| Operation → Target / Plan / Observation | Exact immutable binding fingerprints and distinct evidence status; no graph edge supplies execution authority | A declared or derived relationship promoted to authenticated observation or approval |

The table is a candidate for root integration, not a newly implemented guarantee.
Do not replace the current preservation oracle or actual service evidence with
ontology validation. Schema compatibility and edge existence cannot establish
assignment semantics, runtime authentication, effective execution order, or writer
ownership.

Two inspected parser defaults must **not** be imported into our capture pipeline:
`src/lib/rdf/parser.ts` lines 297–300 defaults missing or invalid cardinality to
`one-to-many`; lines 318–319 skips a relationship with unresolved source or target.
That convenience is incompatible with our unknown/preservation contract. The
parser also derives IDs through URI local-name extraction and uncapitalization;
Intune immutable IDs and scoped Atmos identities must retain their current rules.
`validateOntology` checks endpoint existence but does not establish live instance
cardinality or source authenticity. Its Fabric IQ naming restrictions (26 characters,
property-name/type agreement across entities) are product-specific and should not
be imposed on Intune identifiers.

A later visual editor could reuse the draft/validate/explicit-export interaction,
but draft suggestions must remain separate from source capture, normalized facts,
plan effects and authenticated receipts. Unknown relationship targets need visible
placeholders with reasons and coverage, rather than disappearing from the graph.

Selected file SHA-256 values are in `ontology-source-ledger.json`; pinned source
links preserve provenance without incorporating a new UI/ontology dependency.
