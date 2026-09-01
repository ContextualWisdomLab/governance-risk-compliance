# GRC Analytics query contract

## Product boundary

`Ask GRC / Analyze` is a read-only analysis capability. It helps an authorized buyer interpret and compare governed GRC facts; it does not calculate or approve authoritative GRC state through an LLM.

The required end-state evidence path is:

`User question -> verified Keyverse tenant/workspace/principal/purpose -> question decomposition -> ontology concept/relation resolution -> versioned semantic intent -> authoritative fact retrieval -> provenance/lineage expansion -> knowledge-gap detection -> SearXNG candidate research when needed -> official/primary source fetch and validation -> Evidence Graph -> deterministic calculations -> contextual-orchestrator evidence-bound synthesis -> machine-readable result + buyer-facing explanation`

The ontology, semantic layer, and evidence graph are not a second GRC ledger. Policy/Control/Evidence/Risk/Audit/Remediation contexts remain authoritative. `context-graph-contracts` is the candidate released Shared Kernel for cross-product canonical identity, authority, truth-status, bitemporal, provenance, CloudEvents, schema, and conformance coordinates; GRC consumes a released versioned contract through a port/ACL rather than copying foreign authoritative tables. `LineageWeave` may contribute provenance/lineage observations and inferred evidence through a versioned port/ACL. Inferred or proposed relations never become authoritative merely because an LLM or lineage service produced them.

SearXNG is discovery infrastructure only. Search snippets, rankings, generated summaries, cached fragments, and model descriptions are not evidence. A candidate source enters the Evidence Graph only after source fetch, content/type validation, provenance capture, authority assessment, and citation coordinates are available. Official or primary sources are preferred for external compliance facts. Prompt-injection text found in an internal document, fetched page, search result, metadata field, or evidence attachment is treated as data and cannot alter authorization, tool policy, or the analysis plan.

This increment implements the versioned semantic intent and deterministic planning boundary only. It adds no ontology resolver, LineageWeave adapter, SearXNG connector, source validator, Evidence Graph store, model provider, or database executor.

## Responsibility split

The LLM path through `contextual-orchestrator` may decompose a question, propose ontology concepts/relations, map language to a semantic intent, plan research, select evidence for explanation, and synthesize an evidence-bound answer. It does not become numerical, authorization, compliance, audit, or business truth.

PostgreSQL/read models and deterministic code calculate measures, aggregates, filters, temporal selection, risk/control values, and result digests. A model may not emit raw SQL for direct execution. Risk acceptance, control approval, audit closure, policy publication, finding disposition, compliance/certification status, tenant authority, and security decisions remain authoritative domain workflows outside Analytics.

## Version-one semantic contract

Intent schema: `cwl.grc.analytics.intent.v1`

Query-plan schema: `cwl.grc.analytics.query-plan.v1`

Read-model coordinate: `cwl.grc.analytics.read-model.v1`

Stable dimensions currently admitted by the planning contract cover framework/edition, obligation/jurisdiction, policy/status, internal control/type/frequency/owner, implementation/system scope, evidence source/period/freshness/quality, control test/result/effectiveness, risk category/treatment/acceptance, audit program/engagement/finding/severity, remediation status/due date/verification, tenant/workspace, `effective_time`, and `recorded_time`.

Stable measures currently admitted are `record_count`, `evidence_age_days`, `evidence_record_count`, `control_test_count`, `inherent_risk`, `residual_risk`, `kri_value`, `open_finding_count`, and `remediation_item_count`. Admitting a code to the semantic contract does not make a value available: the planner returns `insufficient_evidence` until an authorized deterministic projection supplies that field.

Every future semantic dimension/measure definition must identify its version, source fields/read model, deterministic formula where applicable, null semantics, effective/system-time semantics, authorization scope, and data-classification/purpose constraints. An LLM-proposed measure name is not a measure until it is in this reviewed versioned contract and backed by deterministic implementation/evidence.

Version one accepts equality and bounded membership filters only. It requires at least one measure, rejects duplicate or unknown semantic fields, and rejects more than 500 result rows. An intent may carry at most 64 filters, and each filter may carry at most 100 values; dimension and measure tuples are also bounded by their versioned allowlists before their contents are scanned. These are planning-resource bounds as well as semantic-contract bounds, so malformed or hostile intents cannot force unbounded collection walks before typed abstention. A time range is optional. When one is supplied, its endpoints must be timezone-aware and its axis must be either effective/business time or system-recorded time. Question text is represented by a SHA-256 hash in the planning contract; raw question or evidence text does not need to enter deterministic query planning.

## Ontology and truth status — next slices

Ontology resolution must preserve provenance and relation truth status. The minimum relation states are `authoritative`, `observed`, `inferred`, `proposed`, `superseded`, and `rejected`. A relation records origin plus valid/effective and system/recorded time where meaningful. Promotion into an authoritative state requires the owning domain workflow; Analytics and `contextual-orchestrator` cannot promote it automatically.

Ontology resolution may map a buyer phrase such as “접근통제”, “control owner”, or “잔여 위험” to versioned concepts and relationships, but ambiguity produces a bounded candidate set or typed abstention rather than silently selecting a different GRC object. Foreign object identities remain canonical references; no cross-service SQL or copied foreign truth tables are introduced for convenience.

## Authorization and abstention

The planner receives verified principal, tenant, workspace, purpose, authorization decision reference, permitted semantic fields, and currently available projection fields. It does not infer identity from headers and does not broaden the requested field set.

Typed fail-closed outcomes are:

- `not_authorized`: requested fields exceed the verified field policy;
- `insufficient_evidence`: requested fields are authorized but unavailable in the current read projection or required validated evidence is absent;
- `unsupported_analysis`: schema, runtime intent shape, identifier, hash, semantic field, filter, time axis, or request bound is unsupported.

These outcomes are part of the product contract. A later contextual-orchestrator synthesis adapter must preserve them rather than converting them into guessed answers.

## Deterministic execution contract — next slice

The next executor must consume only the versioned query plan. It must not accept model-produced raw SQL. The preferred implementation is a versioned semantic DSL mapped to allowlisted read-only views/materialized projections. Any SQL translation must use an AST/parser boundary, bind parameters, explicit table/column allowlists, mandatory tenant/workspace/purpose predicates, `SELECT`-only enforcement, bounded joins/depth, row/byte/time/cost limits, statement timeout, cancellation, and concurrency limits. It must use a read-only database role rather than an application write credential.

`INSERT`, `UPDATE`, `DELETE`, DDL, `COPY`, extension/function execution, arbitrary schemas, system catalogs, secret/config tables, multi-statements, comment/encoding bypasses, unbounded recursive CTEs, and unsafe functions are outside the analytics execution contract.

## Truth, provenance, and external evidence

Analytics reads projections of authoritative GRC contexts. It does not own a new policy, control, evidence, risk, or audit ledger. A framework row or evidence record must not be automatically treated as an effective internal control, satisfied obligation, accepted risk, closed finding, or compliance decision.

The Evidence Graph keeps internal authoritative facts, ontology relations, observed/inferred lineage evidence, externally validated source evidence, and model-produced proposals distinguishable. It does not overwrite their authority classes into one undifferentiated RAG chunk store. When systematic external research is required, the research receipt records query/version, candidate result coordinates, selected source, fetch time, validation result, content digest, provenance/lineage, authority class, relevant valid/system time, and citation coordinates. A search snippet alone cannot satisfy an evidence requirement.

Future query receipts must bind at least analysis request, verified principal/tenant/workspace/purpose, question hash, normalized intent, ontology/semantic contract versions, plan/schema version, executed query/hash, source revision/snapshot time, filters, row/count summary, result digest, evidence/provenance references, external research receipts where used, contextual-orchestrator trace ID, provider/model identifier, prompt/template/config version, generation time, and authorization decision reference.

## Evaluation gate

The production gate will include deterministic golden questions and expected ontology/intent/plan/query equivalence, exact aggregate comparisons, cross-tenant leakage zero, unauthorized-field leakage zero, unsupported-claim hallucination zero, evidence citation precision/coverage, source-authority classification, external-source fetch/provenance validation, temporal `as_of` correctness, prompt-injection resistance across documents/search results/web content, malformed-output handling, query/search budgets/timeouts/cancellation, idempotent repeated requests, provider failure fallback, stale/read-replica lag indicators, large-result behavior, and Korean/English questions.

Numerical correctness is compared with deterministic query results. Model judges may supplement but do not replace golden fixtures, source-grounded assertions, and human-reviewed factual cases.

## Buyer surface — planned

The buyer surface will show the active tenant/workspace/framework/time window, filters, evidence/provenance, ontology/semantic interpretation where material, calculation method, source authority, limitations, and next actions beside exact-value tables and JSON/CSV export. Follow-up questions will reference an explicit prior analysis receipt; hidden conversation state may not silently widen query or research scope.
