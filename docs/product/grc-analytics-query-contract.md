# GRC Analytics query contract

## Product boundary

`Ask GRC / Analyze` is a read-only analysis capability. It helps an authorized buyer interpret and compare governed GRC facts; it does not calculate or approve authoritative GRC state through an LLM.

The end-state pipeline is:

`User question -> verified Keyverse principal/tenant/workspace/purpose -> analytics intent schema -> permitted dimensions/measures/time/filter scope -> deterministic query plan -> policy/tenant/purpose authorization -> read-only query execution -> bounded result set/statistics -> provenance/evidence binding -> contextual-orchestrator grounded synthesis -> machine-readable result + buyer-facing explanation`

This increment implements the versioned intent and deterministic planning boundary only. No model provider or database executor is added.

## Version-one semantic contract

Intent schema: `cwl.grc.analytics.intent.v1`

Query-plan schema: `cwl.grc.analytics.query-plan.v1`

Read-model coordinate: `cwl.grc.analytics.read-model.v1`

Stable dimensions currently admitted by the planning contract cover framework/edition, obligation/jurisdiction, policy/status, internal control/type/frequency/owner, implementation/system scope, evidence source/period/freshness/quality, control test/result/effectiveness, risk category/treatment/acceptance, audit program/engagement/finding/severity, remediation status/due date/verification, tenant/workspace, `effective_time`, and `recorded_time`.

Stable measures currently admitted are `record_count`, `evidence_age_days`, `evidence_record_count`, `control_test_count`, `inherent_risk`, `residual_risk`, `kri_value`, `open_finding_count`, and `remediation_item_count`. Admitting a code to the semantic contract does not make a value available: the planner returns `insufficient_evidence` until an authorized deterministic projection supplies that field.

Version one accepts equality and bounded membership filters only. It requires at least one measure, rejects duplicate or unknown semantic fields, and rejects more than 500 result rows. An intent may carry at most 64 filters, and each filter may carry at most 100 values; dimension and measure tuples are also bounded by their versioned allowlists before their contents are scanned. These are planning-resource bounds as well as semantic-contract bounds, so malformed or hostile intents cannot force unbounded collection walks before typed abstention. A time range is optional. When one is supplied, its endpoints must be timezone-aware and its axis must be either effective/business time or system-recorded time. Question text is represented by a SHA-256 hash in the planning contract; raw question or evidence text does not need to enter deterministic query planning.

## Authorization and abstention

The planner receives verified principal, tenant, workspace, purpose, authorization decision reference, permitted semantic fields, and currently available projection fields. It does not infer identity from headers and does not broaden the requested field set.

Typed fail-closed outcomes are:

- `not_authorized`: requested fields exceed the verified field policy;
- `insufficient_evidence`: requested fields are authorized but unavailable in the current read projection;
- `unsupported_analysis`: schema, runtime intent shape, identifier, hash, semantic field, filter, time axis, or request bound is unsupported.

These outcomes are part of the product contract. A later contextual-orchestrator synthesis adapter must preserve them rather than converting them into guessed answers.

## Deterministic execution contract — next slice

The next executor must consume only the versioned query plan. It must not accept model-produced raw SQL. The preferred implementation is a versioned semantic DSL mapped to allowlisted read-only views/materialized projections. Any SQL translation must use an AST/parser boundary, bind parameters, explicit table/column allowlists, mandatory tenant/workspace/purpose predicates, `SELECT`-only enforcement, bounded joins/depth, row/byte/time/cost limits, statement timeout, cancellation, and concurrency limits. It must use a read-only database role rather than an application write credential.

`INSERT`, `UPDATE`, `DELETE`, DDL, `COPY`, extension/function execution, arbitrary schemas, system catalogs, secret/config tables, multi-statements, comment/encoding bypasses, unbounded recursive CTEs, and unsafe functions are outside the analytics execution contract.

## Truth and provenance

Analytics reads projections of authoritative GRC contexts. It does not own a new policy, control, evidence, risk, or audit ledger. A framework row or evidence record must not be automatically treated as an effective internal control, satisfied obligation, accepted risk, closed finding, or compliance decision.

Future query receipts must bind at least analysis request, verified principal/tenant/workspace/purpose, question hash, normalized intent, plan/schema version, executed query/hash, source revision/snapshot time, filters, row/count summary, result digest, evidence/provenance references, contextual-orchestrator trace ID, provider/model identifier, prompt/template/config version, generation time, and authorization decision reference.

## Evaluation gate

The production gate will include deterministic golden questions and expected plan/query equivalence, exact aggregate comparisons, cross-tenant leakage zero, unauthorized-field leakage zero, unsupported-claim hallucination zero, evidence citation precision/coverage, temporal `as_of` correctness, prompt-injection resistance, malformed-output handling, query budgets/timeouts/cancellation, idempotent repeated requests, provider failure fallback, stale/read-replica lag indicators, large-result behavior, and Korean/English questions.

Numerical correctness is compared with deterministic query results. Model judges may supplement but do not replace golden fixtures and human-reviewed factual cases.

## Buyer surface — planned

The buyer surface will show the active tenant/workspace/framework/time window, filters, evidence/provenance, calculation method, limitations, and next actions beside exact-value tables and JSON/CSV export. Follow-up questions will reference an explicit prior analysis receipt; hidden conversation state may not silently widen query scope.
