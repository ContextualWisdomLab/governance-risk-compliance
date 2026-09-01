# ADR 0012: Keep GRC Analytics as a read-only supporting bounded context

- Status: Accepted
- Date: 2026-08-31
- Decision owners: ContextualWisdomLab GRC maintainers

## Context

GRC buyers need to ask natural-language questions across policy, external requirements, internal controls, evidence, control tests, risk, audit findings, and remediation. Those questions must not turn an LLM into a second GRC system of record or permit model-generated SQL to cross tenant, purpose, or data-classification boundaries.

The authoritative Policy, Control, Evidence, Risk, Audit, and related contexts retain ownership of state and state transitions. `contextual-orchestrator` owns provider selection and model execution. GRC must therefore expose a narrow analytics contract that can be planned, authorized, executed, reproduced, and audited without giving a model write authority or direct database authority.

## Decision

Create `cwl_grc.analytics` as a **Supporting Bounded Context** with explicit `domain` and `application` layers.

The Analytics context owns only versioned semantic intent, deterministic query-plan, result, provenance, and query-receipt contracts. It does not own policy/control/evidence/risk/audit source tables, provider credentials, model clients, or authoritative GRC commands.

The first slice implements `cwl.grc.analytics.intent.v1` and `cwl.grc.analytics.query-plan.v1`. A plan contains allowlisted dimensions, measures, filters, an explicit business/effective or system-recorded time axis, verified principal/tenant/workspace/purpose coordinates, an authorization-decision reference, and a bounded result limit. It contains no raw SQL field.

Natural-language processing and grounded answer synthesis must cross an Anti-Corruption Layer to `contextual-orchestrator`. The GRC repository must not directly call OpenAI, Anthropic, NVIDIA NIM, OpenRouter, Bytez, or another provider API for interactive analytics. The orchestration boundary may propose a structured intent; GRC validates and authorizes that intent before any read execution.

A future executor may translate the versioned semantic plan into allowlisted read-only projections. It must use a read-only database role/transaction and enforce tenant and purpose predicates, bind parameters, table/column allowlists, join/depth limits, row/byte/time/cost/concurrency limits, cancellation, and statement timeout. LLM-generated raw SQL is not an execution contract.

The version-one planner fails closed with typed outcomes:

- `not_authorized` when requested semantic fields exceed the verified field policy;
- `insufficient_evidence` when the authorized projection does not contain the requested fields;
- `unsupported_analysis` for unsupported schema versions, semantic fields, operators, temporal axes, invalid receipt identifiers, invalid question hashes, or out-of-bounds requests.

A framework requirement row, evidence record, or evidence binding is never equivalent to control effectiveness or compliance status. Risk scores, control-effectiveness values, freshness calculations, aggregates, filters, sorting, and temporal selection are deterministic read-model/executor responsibilities rather than LLM calculations.

## DDD boundary

`cwl_grc.analytics.domain` may not depend on the existing flat application/kernel modules, database adapters, SQLAlchemy, or model-provider libraries. `cwl_grc.analytics.application` may depend on the Analytics domain but still does not own persistence or provider adapters. Architectural fitness tests enforce these dependency directions and reject generic `utils`, `helpers`, `services`, `common`, or `misc` buckets inside the Analytics context.

The current flat `cwl_grc` kernel remains legacy structure outside this bounded slice; this ADR does not justify copying that layout into new GRC contexts. Later DDD migrations must be coherent, compatibility-preserving moves rather than cosmetic churn.

## Consequences

The first analytics increment is intentionally non-executable: it establishes the safe semantic and authorization boundary before a read model or LLM adapter exists. This prevents a buyer-facing chat surface from being wired directly to product tables or provider APIs.

The next slices are: canonical read projections over reviewed GRC truth; a safe DSL-to-query executor; versioned structured results/query receipts; provenance/evidence binding; contextual-orchestrator ACL integration; RAG for authorized unstructured evidence; deterministic golden/evaluation fixtures; and the `Ask GRC / Analyze` buyer surface.

## Rejected alternatives

**Direct model-to-database SQL** was rejected because prompt content cannot safely define database authority, tenant predicates, cost bounds, or schema access.

**A generic `ai` or `analytics` utility module in the flat kernel** was rejected because it mixes provider orchestration, semantic planning, persistence, and GRC domain responsibility into one technical bucket.

**Replicating GRC product tables into a second analytics ledger** was rejected because it creates competing truth. Read replicas, materialized read models, and event/outbox projections may be introduced only with explicit provenance and freshness contracts.

**Calculating risk/compliance truth in prompts** was rejected because model output is not a reproducible numerical or governance authority.
